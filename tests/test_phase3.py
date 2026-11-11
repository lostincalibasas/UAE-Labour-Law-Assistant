"""Resilience tests: mocked services and temporary index fixtures only."""

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, Mock, patch

import openai

import eval_answers
import evaluate
import generate_answer as generation
import retrieve_bge as retrieval
from evidence_citations import FALLBACK, build_evidence, resolve_answer
from rag_errors import ERRORS, RAGError, operational_failure

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'sk-secret-do-not-display'
PRIVATE = 'Alice salary and passport details'
CHUNKS = [{'source_document': 'Law', 'article': 'Article 1',
           'filename': 'law.pdf', 'text': 'A supporting passage.', 'distance': 0.2}]


def completion(content='A rule [E1].', finish_reason='stop', **message_fields):
    return NS(choices=[NS(finish_reason=finish_reason,
                         message=NS(role='assistant', content=content, **message_fields))])


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.chat.completions.create.return_value = completion()
        self.retrieve = self.enterContext(patch.object(generation, 'retrieve_chunks', return_value=CHUNKS))
        self.factory = self.enterContext(patch.object(generation, 'get_api_client', return_value=self.client))

    def assert_failure(self, result, code):
        self.assertEqual(result['status'], 'operational_error')
        self.assertEqual(result['error']['code'], code)
        self.assertEqual(result['answer'], '')
        self.assertEqual(result['citations'], [])
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['citation_validation']['status'], 'not_evaluated')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_success_keeps_evidence_validation_and_outcome(self):
        result = generation.generate_answer('test')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['citation_validation']['status'], 'valid')
        self.assertIsNone(result['error'])
        self.client.__exit__.assert_called_once()

    def test_no_evidence_and_bad_citations_are_not_service_failures(self):
        self.retrieve.return_value = []
        result = generation.generate_answer('test')
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertEqual(result['answer'], FALLBACK)
        self.factory.assert_not_called()
        self.retrieve.return_value = CHUNKS
        for text in ('Uncited rule.', 'Invented reference [E100].', FALLBACK):
            self.client.chat.completions.create.return_value = completion(text)
            result = generation.generate_answer('test')
            self.assertEqual(result['status'], 'insufficient_evidence')
            self.assertIsNone(result['error'])

    def test_all_sdk_failure_categories_are_safe_and_not_retried(self):
        request = NS(url='https://api.deepseek.com', headers={'authorization': SECRET})
        response = NS(request=request, status_code=500, headers={})
        cases = [
            (openai.APIConnectionError(message=SECRET + PRIVATE, request=request), 'api_connection'),
            (openai.APITimeoutError(request=request), 'api_timeout'),
            (openai.AuthenticationError(SECRET, response=response, body=PRIVATE), 'api_authentication'),
            (openai.PermissionDeniedError(SECRET, response=response, body=PRIVATE), 'api_authentication'),
            (openai.RateLimitError(SECRET, response=response, body=PRIVATE), 'api_rate_limit'),
            (openai.InternalServerError(SECRET, response=response, body=PRIVATE), 'api_server'),
            (openai.BadRequestError(SECRET, response=response, body=PRIVATE), 'api_request'),
            (openai.APIResponseValidationError(response, PRIVATE, message=SECRET), 'api_response_invalid'),
            (RuntimeError(SECRET + PRIVATE), 'internal_error'),
        ]
        for error, code in cases:
            with self.subTest(code=code):
                self.client.chat.completions.create.reset_mock()
                self.client.chat.completions.create.side_effect = error
                with self.assertLogs('compliance_rag', level='WARNING') as logs:
                    result = generation.generate_answer(PRIVATE)
                self.assert_failure(result, code)
                self.client.chat.completions.create.assert_called_once()
                self.assertNotIn(SECRET, str(logs.output))
                self.assertNotIn(PRIVATE, str(logs.output))
                event = json.loads(logs.records[0].getMessage())
                self.assertEqual(set(event), {'event', 'stage', 'code', 'retryable'})
                self.assertIsNone(logs.records[0].exc_info)

    def test_empty_malformed_and_truncated_responses_never_pass(self):
        cases = [
            (completion(''), 'api_response_empty'),
            (completion('  '), 'api_response_empty'),
            (completion(None), 'api_response_empty'),
            (completion(['A rule [E1]']), 'api_response_invalid'),
            (None, 'api_response_invalid'),
            ({'choices': []}, 'api_response_invalid'),
            (NS(choices=[]), 'api_response_invalid'),
            (NS(choices=[completion().choices[0]] * 2), 'api_response_invalid'),
            (NS(choices=[NS(finish_reason='stop')]), 'api_response_invalid'),
            (completion(finish_reason=None), 'api_response_invalid'),
            (completion(finish_reason='length'), 'api_response_truncated'),
            (completion(finish_reason='content_filter'), 'api_response_invalid'),
            (completion(finish_reason='tool_calls'), 'api_response_invalid'),
            (completion(tool_calls=[{'name': 'unexpected'}]), 'api_response_invalid'),
            (completion(refusal='Refused'), 'api_response_invalid'),
        ]
        for response, code in cases:
            with self.subTest(response=response):
                self.client.chat.completions.create.return_value = response
                with self.assertLogs('compliance_rag'):
                    self.assert_failure(generation.generate_answer('test'), code)

    def test_retrieval_and_configuration_failures_skip_api(self):
        for code in ('index_missing', 'collection_missing', 'collection_empty', 'retrieval_unavailable', 'embedding_unavailable'):
            self.retrieve.side_effect = RAGError(code, 'retrieval')
            with self.assertLogs('compliance_rag'):
                self.assert_failure(generation.generate_answer('test'), code)
        self.factory.assert_not_called()
        self.retrieve.side_effect = None
        self.factory.side_effect = RAGError('configuration_missing', 'configuration')
        with self.assertLogs('compliance_rag'):
            self.assert_failure(generation.generate_answer('test'), 'configuration_missing')
        self.client.chat.completions.create.assert_not_called()

    def test_unexpected_retrieval_error_is_sanitized(self):
        self.retrieve.side_effect = RuntimeError(SECRET + PRIVATE)
        with self.assertLogs('compliance_rag'):
            self.assert_failure(generation.generate_answer(PRIVATE), 'retrieval_unavailable')

    def test_invalid_input_does_not_call_services(self):
        for query, k in (('', 10), (' ', 10), (None, 10), ('test', 0), ('test', True)):
            with self.assertLogs('compliance_rag'):
                self.assert_failure(generation.generate_answer(query, k), 'invalid_input')
        self.retrieve.assert_not_called()
        self.factory.assert_not_called()


class InitializationTests(unittest.TestCase):
    def test_imports_do_not_require_models_database_sdk_or_credentials(self):
        with patch.dict(sys.modules, {'openai': None, 'dotenv': None, 'chromadb': None,
                                     'sentence_transformers': None}), patch.dict(os.environ, {}, clear=True):
            runpy.run_path(str(ROOT / 'retrieve_bge.py'), run_name='_import_test')
            runpy.run_path(str(ROOT / 'generate_answer.py'), run_name='_import_test')

    def test_missing_invalid_and_placeholder_keys_are_safe(self):
        with patch('dotenv.load_dotenv'), patch('openai.OpenAI') as factory:
            for key in (None, '', ' ', 'your_deepseek_api_key_here', SECRET + '\n', 'key\x00bad'):
                with self.subTest(key=key), patch.object(generation.os, 'getenv', return_value=key):
                    with self.assertRaises(RAGError) as error:
                        generation.get_api_client()
                    self.assertIn(error.exception.code, ('configuration_missing', 'configuration_invalid'))
                    self.assertNotIn(SECRET, str(error.exception))
            factory.assert_not_called()

    def test_client_uses_finite_timeout_zero_retries_and_current_key(self):
        with patch('dotenv.load_dotenv'), patch('openai.OpenAI') as factory, \
             patch.dict(os.environ, {'DEEPSEEK_API_KEY': SECRET}):
            generation.get_api_client()
        factory.assert_called_once_with(api_key=SECRET, base_url='https://api.deepseek.com',
                                        timeout=30.0, max_retries=0)

    def test_configuration_load_exception_does_not_leak(self):
        with patch('dotenv.load_dotenv', side_effect=OSError(SECRET)):
            with self.assertRaises(RAGError) as error:
                generation.get_api_client()
        self.assertEqual(error.exception.code, 'configuration_invalid')
        self.assertNotIn(SECRET, str(error.exception))


class RetrievalTests(unittest.TestCase):
    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing'
            with patch.object(retrieval, 'DB_PATH', path), patch.object(retrieval, 'client', None):
                with self.assertRaises(RAGError) as error:
                    retrieval.get_collection()
            self.assertEqual(error.exception.code, 'index_missing')
            self.assertFalse(path.exists())

    def test_database_open_and_missing_collection_failures(self):
        class NotFoundError(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'chroma.sqlite3'
            database.write_bytes(b'protected index')
            client = Mock()
            factory = Mock(return_value=client)
            settings = Mock(return_value='validation-only-settings')
            modules = {'chromadb': NS(PersistentClient=factory),
                       'chromadb.config': NS(Settings=settings),
                       'chromadb.errors': NS(NotFoundError=NotFoundError)}
            with patch.dict(sys.modules, modules), patch.object(retrieval, 'DB_PATH', Path(directory)), \
                 patch.object(retrieval, 'client', None):
                client.get_collection.side_effect = NotFoundError(SECRET)
                with self.assertRaises(RAGError) as error:
                    retrieval.get_collection()
                self.assertEqual(error.exception.code, 'collection_missing')
                settings.assert_called_once_with(migrations='validate', anonymized_telemetry=False)
                client.get_or_create_collection.assert_not_called()
                client.create_collection.assert_not_called()
                client.delete_collection.assert_not_called()
                retrieval.client = None
                factory.side_effect = OSError(SECRET)
                with self.assertRaises(RAGError) as error:
                    retrieval.get_collection()
                self.assertEqual(error.exception.code, 'retrieval_unavailable')
                self.assertIsNone(retrieval.client)
            self.assertEqual(database.read_bytes(), b'protected index')

    def test_empty_collection_never_embeds_or_queries(self):
        collection = Mock()
        collection.count.return_value = 0
        with patch.object(retrieval, 'get_collection', return_value=collection), \
             patch.object(retrieval, 'get_model') as model:
            with self.assertRaises(RAGError) as error:
                retrieval.retrieve_chunks('test')
        self.assertEqual(error.exception.code, 'collection_empty')
        collection.query.assert_not_called()
        model.assert_not_called()

    def test_count_query_and_embedding_failures_are_safe(self):
        for stage, code in (('count', 'retrieval_unavailable'), ('query', 'retrieval_unavailable'),
                            ('encode', 'embedding_unavailable')):
            with self.subTest(stage=stage):
                collection, model = Mock(), Mock()
                collection.count.return_value = 1
                (model.encode if stage == 'encode' else getattr(collection, stage)).side_effect = RuntimeError(SECRET)
                with patch.object(retrieval, 'get_collection', return_value=collection), \
                     patch.object(retrieval, 'get_model', return_value=model):
                    with self.assertRaises(RAGError) as error:
                        retrieval.retrieve_chunks('test')
                self.assertEqual(error.exception.code, code)
                self.assertNotIn(SECRET, str(error.exception))

    def test_model_loading_failure_can_be_retried(self):
        factory = Mock(side_effect=[OSError(SECRET), Mock()])
        with patch.dict(sys.modules, {'sentence_transformers': NS(SentenceTransformer=factory)}), \
             patch.object(retrieval, 'model', None):
            with self.assertRaises(RAGError) as error:
                retrieval.get_model()
            self.assertEqual(error.exception.code, 'embedding_unavailable')
            self.assertIsNone(retrieval.model)
            retrieval.get_model()
            self.assertIsNotNone(retrieval.model)

    def test_retrieval_settings_and_metadata_are_preserved(self):
        collection, model = Mock(), Mock()
        collection.count.return_value = 1
        model.encode.return_value.tolist.return_value = [0.1, 0.2]
        collection.query.return_value = {'documents': [['passage']],
            'metadatas': [[{'source_document': 'Law', 'article': 'Article 1', 'filename': 'law.pdf'}]],
            'distances': [[0.2]]}
        with patch.object(retrieval, 'get_collection', return_value=collection), \
             patch.object(retrieval, 'get_model', return_value=model):
            result = retrieval.retrieve_chunks('test', top_k=10)
        model.encode.assert_called_once_with(retrieval.QUERY_PREFIX + 'test', normalize_embeddings=True)
        collection.query.assert_called_once_with(query_embeddings=[[0.1, 0.2]], n_results=1,
                                                 include=['documents', 'metadatas', 'distances'])
        self.assertEqual(result[0], {**CHUNKS[0], 'text': 'passage'})

    def test_malformed_database_results_do_not_become_empty_evidence(self):
        collection = Mock()
        collection.count.return_value = 1
        for response in ({}, {'documents': [['passage']], 'metadatas': [[]], 'distances': [[0.1]]},
                         {'documents': [['passage']], 'metadatas': [[{}]], 'distances': [[0.1]]}):
            collection.query.return_value = response
            with patch.object(retrieval, 'get_collection', return_value=collection), \
                 patch.object(retrieval, 'get_model', return_value=Mock()):
                with self.assertRaises(RAGError) as error:
                    retrieval.retrieve_chunks('test')
            self.assertEqual(error.exception.code, 'retrieval_invalid')


class UIAndEvaluationTests(unittest.TestCase):
    def render(self, result=None, error=None, clicked=True):
        st = MagicMock()
        st.button.return_value = clicked
        st.text_input.return_value = 'test'
        generate = Mock(return_value=result, side_effect=error)
        with patch.dict(sys.modules, {'streamlit': st, 'generate_answer': NS(generate_answer=generate)}), \
             patch.dict(os.environ):
            runpy.run_path(str(ROOT / 'app.py'), run_name='_phase3_app')
        return st, generate

    def test_ui_loads_without_initializing_services(self):
        st, generate = self.render(error=RuntimeError(SECRET), clicked=False)
        generate.assert_not_called()
        st.error.assert_not_called()

    def test_ui_all_operational_errors_show_actions_not_legal_answers(self):
        for code in ERRORS:
            with self.subTest(code=code), self.assertLogs('compliance_rag'):
                failure = operational_failure(RAGError(code, 'generation'))
            # Even unsafe caller-provided messages are ignored by the UI.
            failure['error']['message'] = SECRET
            st, _ = self.render(failure)
            st.error.assert_called_once_with(ERRORS[code][0])
            st.write.assert_not_called()
            st.expander.assert_not_called()
            self.assertNotIn(SECRET, str(st.mock_calls))

    def test_ui_unexpected_failure_is_caught_without_leaking(self):
        with self.assertLogs('compliance_rag') as logs:
            st, _ = self.render(error=RuntimeError(SECRET + PRIVATE))
        st.error.assert_called_once_with(ERRORS['internal_error'][0])
        self.assertNotIn(SECRET, str(logs.output) + str(st.mock_calls))

    def test_ui_distinguishes_evidence_fallback_from_valid_answer(self):
        st, _ = self.render(resolve_answer('Uncited', build_evidence(CHUNKS)))
        st.info.assert_any_call(FALLBACK)
        st.error.assert_not_called()
        st.write.assert_not_called()
        st, _ = self.render(resolve_answer('A rule [E1].', build_evidence(CHUNKS)))
        st.write.assert_called_once_with('A rule [E1].')
        st.error.assert_not_called()

    def test_evaluator_does_not_score_api_failure_as_abstention(self):
        case = {'id': 'E1', 'category': 'test', 'question': 'test', 'answerable': False,
                'expected_source_document': None, 'expected_article': None, 'expected_key_facts': ''}
        with self.assertLogs('compliance_rag'):
            failure = operational_failure(RAGError('api_timeout', 'generation'))
        with patch.object(evaluate, 'retrieve_chunks', return_value=CHUNKS):
            result = evaluate.evaluate_case(case, Mock(return_value=failure))
        self.assertEqual(result['status'], 'operational_error')
        self.assertIsNone(result['fallback_pass'])
        self.assertEqual(evaluate.summarize([result], False)['errors'], 1)

    def test_evaluator_sanitizes_unexpected_retrieval_failure(self):
        case = {'id': 'E1', 'category': 'test', 'question': 'test', 'answerable': True,
                'expected_source_document': 'Law', 'expected_article': 'Article 1', 'expected_key_facts': ''}
        with patch.object(evaluate, 'retrieve_chunks', side_effect=RuntimeError(SECRET)), \
             self.assertLogs('compliance_rag'):
            result = evaluate.evaluate_case(case)
        self.assertEqual(result['status'], 'operational_error')
        self.assertNotIn(SECRET, json.dumps(result))

    def test_expanded_evaluator_records_failures_without_judging_them(self):
        question = {'id': 'Q1', 'question': 'test', 'category': 'test',
                    'expected_articles': [CHUNKS[0]], 'must_not_cite': []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'new.json'
            with patch('evaluate.retrieve_chunks', side_effect=RAGError('collection_empty', 'retrieval')), \
                 patch.object(eval_answers, 'load_eval_set', return_value=[question]), \
                 patch.object(eval_answers, 'generate_answer') as generate, \
                 patch.object(eval_answers, 'judge_answer') as judge, \
                 contextlib.redirect_stdout(io.StringIO()), self.assertLogs('compliance_rag'):
                eval_answers.cmd_answers(NS(output=output, limit=None, k=10, no_judge=False))
            row = json.loads(output.read_text(encoding='utf-8'))[0]
        generate.assert_not_called()
        judge.assert_not_called()
        self.assertEqual(row['status'], 'operational_error')
        self.assertEqual(row['error']['code'], 'collection_empty')


if __name__ == '__main__':
    unittest.main()
