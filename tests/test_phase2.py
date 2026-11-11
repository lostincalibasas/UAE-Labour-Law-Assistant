"""Evidence reference validation, with mocked generation/retrieval and UI."""

import copy
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, Mock, patch

import eval_answers
import evaluate
from evidence_citations import FALLBACK, build_evidence, resolve_answer


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = [
    {'source_document': 'Federal Decree-Law No. 33 of 2021', 'article': 'Article 9',
     'filename': 'general.pdf', 'text': 'Private-sector probation passage.', 'distance': 0.1},
    {'source_document': 'Federal Decree-Law No. 9 of 2022', 'article': 'Article 43',
     'filename': 'domestic.pdf', 'text': 'A different law and article.', 'distance': 0.2},
    {'source_document': 'Federal Decree-Law No. 33 of 2021', 'article': 'Article 43',
     'filename': 'general.pdf', 'text': 'General notice passage.', 'distance': 0.3},
]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence(copy.deepcopy(CHUNKS))

    def test_correct_id_resolves_exact_metadata_and_excerpt(self):
        result = resolve_answer('A rule [E2].', self.evidence)
        self.assertEqual(result['citation_validation']['status'], 'valid')
        self.assertEqual(result['citations'], [{
            'evidence_id': 'E2', 'source_document': CHUNKS[1]['source_document'],
            'article': 'Article 43', 'filename': 'domestic.pdf',
            'excerpt': CHUNKS[1]['text'],
        }])
        self.assertEqual(result['sources'], [f"{CHUNKS[1]['source_document']} — Article 43"])

    def test_invented_id_rejects_entire_answer_even_with_valid_id(self):
        for answer in ('A rule [E99].', 'A rule [E1, E99].', 'A rule [E0].', 'A rule [E01].'):
            with self.subTest(answer=answer):
                result = resolve_answer(answer, self.evidence)
                self.assertEqual(result['answer'], FALLBACK)
                self.assertEqual(result['citation_validation']['status'], 'invalid_citations')
                self.assertTrue(result['citation_validation']['invalid_ids'])
                self.assertEqual(result['citations'], [])
                self.assertEqual(result['sources'], [])

    def test_wrong_law_article_text_never_constructs_metadata(self):
        answer = (f"{CHUNKS[0]['source_document']}, Article 9 [E1]. "
                  f"{CHUNKS[1]['source_document']}, Article 43 [E2].")
        result = resolve_answer(answer, self.evidence)
        self.assertEqual([c['evidence_id'] for c in result['citations']], ['E1', 'E2'])
        self.assertNotIn(f"{CHUNKS[0]['source_document']} — Article 43", result['sources'])
        # Even false metadata in generated prose cannot change E1's reference.
        result = resolve_answer('Invented Law, Article 999 [E1].', self.evidence)
        self.assertEqual(result['citations'][0]['article'], 'Article 9')
        self.assertEqual(result['citations'][0]['source_document'], CHUNKS[0]['source_document'])
        self.assertEqual(result['claim_support'], 'not_evaluated')

    def test_multiple_and_duplicate_citations_preserve_first_use_order(self):
        result = resolve_answer('Rule [E2, E1]. Another [E2][E3] and [E1].', self.evidence)
        self.assertEqual([c['evidence_id'] for c in result['citations']], ['E2', 'E1', 'E3'])

    def test_different_passages_same_article_keep_separate_excerpts(self):
        chunks = [CHUNKS[0], {**CHUNKS[0], 'text': 'Second fragment of same article.'}]
        result = resolve_answer('Rule [E1, E2].', build_evidence(chunks))
        self.assertEqual(len(result['citations']), 2)
        self.assertEqual(len(result['sources']), 1)
        self.assertNotEqual(result['citations'][0]['excerpt'], result['citations'][1]['excerpt'])

    def test_missing_and_legacy_citations_fall_back(self):
        for answer in ('A factual claim.', f"{CHUNKS[0]['source_document']}, Article 9."):
            with self.subTest(answer=answer):
                result = resolve_answer(answer, self.evidence)
                self.assertEqual(result['answer'], FALLBACK)
                self.assertEqual(result['citation_validation']['status'], 'missing_citations')
                self.assertEqual(result['sources'], [])

    def test_supported_syntax_variations(self):
        for marker in ('[E1]', '[e1]', '[ E1 ]', '(E1)', '[ E 1 ]', '**[E1]**'):
            with self.subTest(marker=marker):
                result = resolve_answer(f'Rule {marker}.', self.evidence)
                self.assertEqual([c['evidence_id'] for c in result['citations']], ['E1'])
        for marker in ('[E1, E2]', '(e1; e2)', '[E1][E2]', '[E1] (E2)'):
            with self.subTest(marker=marker):
                result = resolve_answer(f'Rules {marker}.', self.evidence)
                self.assertEqual([c['evidence_id'] for c in result['citations']], ['E1', 'E2'])

    def test_malformed_ranges_bare_and_partial_ids_are_rejected(self):
        for marker in ('[E1-E3]', 'E1', '[E1foo]', '[E1, unknown]', '[E1', '[E1 E2]'):
            with self.subTest(marker=marker):
                result = resolve_answer(f'Rule [E2]. Another {marker}.', self.evidence)
                self.assertEqual(result['answer'], FALLBACK)
                self.assertEqual(result['citation_validation']['status'], 'invalid_citations')

    def test_no_evidence_and_empty_passages(self):
        self.assertEqual(build_evidence([{'text': ''}, {'text': ' '}, {'text': None}]), [])
        result = resolve_answer('Claim [E1].', [])
        self.assertEqual(result['answer'], FALLBACK)
        self.assertEqual(result['citation_validation']['status'], 'no_evidence')

    def test_missing_article_is_not_invented(self):
        for article in (None, '', 'unknown'):
            result = resolve_answer('Rule [E1].', build_evidence([{**CHUNKS[0], 'article': article}]))
            self.assertIsNone(result['citations'][0]['article'])
            self.assertEqual(result['sources'], [CHUNKS[0]['source_document']])

    def test_insufficient_evidence_response_discards_extra_claims(self):
        for answer in ('', None, FALLBACK, FALLBACK + ' However, invented claim [E1].'):
            result = resolve_answer(answer, self.evidence)
            self.assertEqual(result['answer'], FALLBACK)
            self.assertEqual(result['citations'], [])
            self.assertEqual(result['citation_validation']['status'], 'insufficient_evidence')

    def test_valid_id_does_not_establish_support_or_pass_semantic_judge(self):
        answer = 'Every worker receives a million dirhams every day [E1].'
        result = resolve_answer(answer, self.evidence)
        self.assertEqual(result['citation_validation']['status'], 'valid')
        self.assertEqual(result['claim_support'], 'not_evaluated')
        response = {'facts': [], 'forbidden': [], 'unsupported_claims': ['Invented wage claim']}
        with patch.object(eval_answers, 'call_judge', return_value=response):
            judged = eval_answers.judge_answer(
                {'question': 'test', 'must_include': [], 'must_not_include': []}, answer, CHUNKS)
        self.assertFalse(judged['scores']['pass'])

    def test_query_local_ids_do_not_reuse_previous_metadata(self):
        first = resolve_answer('Claim [E1].', build_evidence([CHUNKS[0]]))
        second = resolve_answer('Claim [E1].', build_evidence([CHUNKS[1]]))
        self.assertNotEqual(first['citations'][0]['source_document'], second['citations'][0]['source_document'])


class IntegrationTests(unittest.TestCase):
    def load_generator(self, chunks, answer):
        client = MagicMock()
        client.__enter__.return_value = client
        client.chat.completions.create.return_value = NS(choices=[NS(
            finish_reason='stop', message=NS(role='assistant', content=answer))])
        retriever = Mock(return_value=chunks)
        dependencies = {'openai': NS(OpenAI=Mock(return_value=client)),
                        'dotenv': NS(load_dotenv=Mock()),
                        'retrieve_bge': NS(retrieve_chunks=retriever)}
        spec = importlib.util.spec_from_file_location('_phase2_generator', ROOT / 'generate_answer.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, dependencies):
            spec.loader.exec_module(module)
        # Request-time client construction is isolated from credentials/network.
        module.get_api_client = Mock(return_value=client)
        return module, client, retriever

    def test_generator_supplies_structured_evidence_and_preserves_retrieval(self):
        chunks = copy.deepcopy(CHUNKS)
        module, client, retriever = self.load_generator(chunks, 'A rule [E1].')
        result = module.generate_answer('Question?', top_k=3)
        retriever.assert_called_once_with('Question?', top_k=3)
        messages = client.chat.completions.create.call_args.kwargs['messages']
        payload = json.loads(messages[1]['content'])
        self.assertEqual(payload['question'], 'Question?')
        self.assertEqual(payload['evidence'], build_evidence(CHUNKS))
        self.assertIn('immediately after each factual legal claim', messages[0]['content'])
        self.assertEqual(chunks, CHUNKS)
        self.assertEqual(result['citation_validation']['status'], 'valid')

    def test_empty_retrieval_skips_llm(self):
        module, client, _ = self.load_generator([], 'Must never be used')
        result = module.generate_answer('test')
        client.chat.completions.create.assert_not_called()
        self.assertEqual(result['answer'], FALLBACK)
        self.assertEqual(result['citation_validation']['status'], 'no_evidence')

    def test_generation_rejects_hallucinated_id(self):
        module, _, _ = self.load_generator(CHUNKS, 'Claim [E100].')
        result = module.generate_answer('test')
        self.assertEqual(result['answer'], FALLBACK)
        self.assertEqual(result['citation_validation']['invalid_ids'], ['E100'])

    def test_original_evaluator_counts_structured_ids_but_not_legacy_strings(self):
        case = {'id': 'E1', 'category': 'test', 'question': 'test', 'answerable': True,
                'expected_source_document': CHUNKS[0]['source_document'],
                'expected_article': 'Article 9', 'expected_key_facts': 'fact'}
        response = resolve_answer('Rule [E1].', build_evidence(CHUNKS))
        with patch.object(evaluate, 'retrieve_chunks', return_value=CHUNKS):
            verified = evaluate.evaluate_case(case, Mock(return_value=response))
            legacy = evaluate.evaluate_case(case, Mock(return_value={
                'answer': 'Old style citation', 'sources': response['sources']}))
        self.assertTrue(verified['citation_hit'])
        self.assertEqual(verified['claim_support'], 'not_evaluated')
        self.assertFalse(legacy['citation_hit'])
        self.assertEqual(legacy['citation_validation']['status'], 'legacy_unverified')

    def test_expanded_citation_metrics_use_evidence_pairs_and_mark_legacy(self):
        q = {'expected_articles': [CHUNKS[0]], 'must_not_cite': [CHUNKS[1]]}
        response = resolve_answer('Rule [E1].', build_evidence(CHUNKS))
        checked = eval_answers.citation_check(response['answer'], q, response['citations'])
        self.assertEqual(checked['citation_recall'], 1)
        self.assertEqual(checked['wrong_law_flag'], [])
        legacy = eval_answers.citation_check(f"{CHUNKS[0]['source_document']}, Article 9", q)
        self.assertEqual(legacy['verification'], 'legacy_unverified')
        self.assertEqual(legacy['citation_recall'], 0)

    def test_expanded_command_records_full_evidence_response(self):
        response = resolve_answer('Rule [E1].', build_evidence(CHUNKS))
        question = {'id': 'Q1', 'question': 'test', 'category': 'test',
                    'expected_articles': [CHUNKS[0]], 'must_not_cite': []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'new.json'
            with patch('evaluate.retrieve_chunks', return_value=CHUNKS), \
                 patch.object(eval_answers, 'load_eval_set', return_value=[question]), \
                 patch.object(eval_answers, 'generate_answer', return_value=response), \
                 contextlib.redirect_stdout(io.StringIO()):
                eval_answers.cmd_answers(NS(output=output, limit=None, k=10, no_judge=True))
            row = json.loads(output.read_text(encoding='utf-8'))[0]
        self.assertEqual(row['evidence_citations'], response['citations'])
        self.assertEqual(row['citations']['citation_recall'], 1)
        self.assertEqual(row['citation_validation']['status'], 'valid')

    def test_expanded_generation_helper_retains_text_only_default(self):
        response = resolve_answer('Rule [E1].', build_evidence(CHUNKS))
        with patch.dict(sys.modules, {'generate_answer': NS(generate_answer=Mock(return_value=response))}):
            self.assertEqual(eval_answers.generate_answer('test', 10), response['answer'])
            self.assertEqual(eval_answers.generate_answer('test', 10, include_evidence=True), response)

    def render(self, response):
        st = MagicMock()
        st.text_input.return_value = 'Question?'
        st.button.return_value = True
        with patch.dict(sys.modules, {'streamlit': st, 'generate_answer': NS(generate_answer=Mock(return_value=response))}), \
             patch.dict(os.environ):
            runpy.run_path(str(ROOT / 'app.py'), run_name='_phase2_app')
        return st

    def test_ui_displays_exact_excerpts_and_support_limitation(self):
        result = resolve_answer('Rule [E2].', build_evidence(CHUNKS))
        st = self.render(result)
        st.expander.assert_called_once_with(f"[E2] {CHUNKS[1]['source_document']} — Article 43")
        st.text.assert_called_once_with(CHUNKS[1]['text'])
        self.assertTrue(any('not been automatically checked' in call.args[0]
                            for call in st.caption.call_args_list))

    def test_ui_does_not_show_legacy_sources_as_verified(self):
        st = self.render({'answer': 'Old answer', 'sources': ['Law — Article 1']})
        st.expander.assert_not_called()
        st.caption.assert_any_call('No verified evidence citations available.')


if __name__ == '__main__':
    unittest.main()
