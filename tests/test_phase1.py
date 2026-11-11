"""Phase 1 regressions: no network, model downloads, or live database access."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import artifact_io
import build_eval_set
import compare_embedding_models as comparison
import eval_answers
import evaluate


class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'results' / 'new.json'
        self.console = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.console))
        self.enterContext(contextlib.redirect_stderr(self.console))

    def cli(self, module, *args):
        with patch.object(sys, 'argv', [module.__name__, *map(str, args)]):
            module.main()

    def existing_file(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b'preserve these exact bytes')
        return self.output.read_bytes()

    def question(self):
        return {'id': 'Q1', 'question': 'test', 'category': 'single_fact',
                'expected_articles': [{'source_document': 'Law', 'article': 'Article 1'}],
                'must_include': [], 'must_not_include': []}

    def test_json_creates_parents_and_round_trips_unicode(self):
        artifact_io.write_new_json(self.output, {'text': 'law \u2014 article'})
        self.assertEqual(json.loads(self.output.read_text(encoding='utf-8')),
                         {'text': 'law \u2014 article'})

    def test_existing_file_is_preserved(self):
        original = self.existing_file()
        with self.assertRaises(FileExistsError):
            artifact_io.write_new_json(self.output, {'replacement': True})
        self.assertEqual(self.output.read_bytes(), original)

    def test_exclusive_write_handles_race_after_preflight(self):
        def concurrent_writer(path):
            self.existing_file()
            return Path(path)
        with patch.object(artifact_io, 'require_new_output', side_effect=concurrent_writer):
            with self.assertRaises(FileExistsError):
                artifact_io.write_new_json(self.output, {})
        self.assertEqual(self.output.read_bytes(), b'preserve these exact bytes')

    def test_invalid_json_does_not_create_output(self):
        with self.assertRaises(TypeError):
            artifact_io.write_new_json(self.output, object())
        self.assertFalse(self.output.exists())

    def test_all_evaluation_commands_refuse_existing_output_before_work(self):
        original = self.existing_file()
        with patch.object(evaluate, 'retrieve_chunks') as retrieve, \
             patch.object(eval_answers, 'load_eval_set') as load_set, \
             patch.object(comparison, 'load_json') as load_comparison:
            for module, args in (
                (evaluate, ['--retrieval-only']),
                (eval_answers, ['answers', '--no-judge']),
                (eval_answers, ['retrieval']),
                (eval_answers, ['audit']),
                (comparison, []),
            ):
                with self.subTest(command=[module.__name__, *args]):
                    with self.assertRaises(SystemExit) as error:
                        self.cli(module, *args, '--output', self.output)
                    self.assertEqual(error.exception.code, 2)
                    self.assertEqual(self.output.read_bytes(), original)
            retrieve.assert_not_called()
            load_set.assert_not_called()
            load_comparison.assert_not_called()

    def test_original_evaluator_writes_explicit_output(self):
        dataset = self.root / 'questions.json'
        dataset.write_text(json.dumps([{
            'id': 'E1', 'category': 'test', 'question': 'test', 'answerable': True,
            'expected_source_document': 'Law', 'expected_article': 'Article 1',
            'expected_key_facts': 'fact',
        }]), encoding='utf-8')
        with patch.object(evaluate, 'retrieve_chunks', return_value=[{
            'source_document': 'Law', 'article': 'Article 1', 'text': 'fact',
        }]):
            self.cli(evaluate, '--retrieval-only', '--dataset', dataset, '--output', self.output)
        report = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertEqual(report['summary']['retrieval_hit_at_10']['passed'], 1)

    def test_expanded_retrieval_writes_explicit_output(self):
        with patch.object(eval_answers, 'load_eval_set', return_value=[]), \
             patch.object(eval_answers, 'run_retrieval', return_value=({'Q1': {}}, {})), \
             patch.object(eval_answers, 'print_retrieval'):
            eval_answers.cmd_retrieval(SimpleNamespace(output=self.output, k=[10]))
        self.assertEqual(json.loads(self.output.read_text()), {'Q1': {}})

    def test_expanded_answers_writes_explicit_output(self):
        retriever = SimpleNamespace(retrieve_chunks=Mock(return_value=[{
            'source_document': 'Law', 'article': 'Article 1', 'text': 'fact',
        }]))
        with patch.object(evaluate, 'retrieve_chunks', retriever.retrieve_chunks), \
             patch.object(eval_answers, 'load_eval_set', return_value=[self.question()]), \
             patch.object(eval_answers, 'generate_answer', return_value='test'), \
             patch.object(eval_answers, 'print_retrieval'):
            eval_answers.cmd_answers(SimpleNamespace(output=self.output, k=10, limit=None, no_judge=True))
        rows = json.loads(self.output.read_text())
        self.assertEqual(rows[0]['id'], 'Q1')
        self.assertNotIn('judge', rows[0])

    def test_judge_requires_supported_complete_correct_answer(self):
        question = self.question()
        question['must_include'] = [{'fact': 'required fact'}]
        question['must_not_include'] = ['forbidden fact']
        for verdict, triggered, unsupported, expected in (
            ('present', False, [], True),
            ('present', False, ['invented claim'], False),
            ('missing', False, [], False),
            ('contradicted', False, [], False),
            ('present', True, [], False),
        ):
            with self.subTest(verdict=verdict, triggered=triggered, unsupported=unsupported):
                response = {'facts': [{'id': 0, 'verdict': verdict, 'evidence_ids': ['E1'], 'reason': 'checked'}],
                            'forbidden': [{'id': 0, 'triggered': triggered, 'reason': 'checked'}],
                            'claims': [{'id': 0, 'quote': 'answer [E1]', 'evidence_ids': ['E1'], 'verdict': 'supported', 'wrong_law': False, 'reason': 'checked'}],
                            'evidence_sufficient': True, 'answer_correct': True,
                            'unsupported_claims': unsupported}
                with patch.object(eval_answers, 'call_judge', return_value=response):
                    result = eval_answers.judge_answer(question, 'answer [E1]', [{'evidence_id': 'E1', 'text': 'fact'}])
                self.assertIs(result['scores']['pass'], expected)

    def test_audit_empty_or_unjudged_results_do_not_prompt_or_write(self):
        source = self.root / 'answers.json'
        for rows in ([], [{'id': 'Q1'}], [{'id': 'Q1', 'judge': None}]):
            with self.subTest(rows=rows):
                source.write_text(json.dumps(rows), encoding='utf-8')
                with patch('builtins.input') as prompt:
                    self.cli(eval_answers, 'audit', '--input', source, '--output', self.output)
                prompt.assert_not_called()
                self.assertFalse(self.output.exists())
        self.assertIn('No judged results', self.console.getvalue())

    def test_audit_samples_only_judged_rows_and_preserves_input(self):
        source = self.root / 'answers.json'
        rows = [{'id': 'unjudged'}, {'id': 'Q1', 'answer': 'answer',
                'judge': {'facts': [], 'scores': {'pass': True}}}]
        source.write_text(json.dumps(rows), encoding='utf-8')
        original = source.read_bytes()
        with patch.object(eval_answers, 'load_eval_set', return_value=[self.question()]), \
             patch('builtins.input', return_value='y') as prompt:
            self.cli(eval_answers, 'audit', '--input', source, '--n', 25, '--output', self.output)
        self.assertEqual(prompt.call_count, 1)
        self.assertEqual(json.loads(self.output.read_text()), [
            {'id': 'Q1', 'judge_pass': True, 'human_agrees': True, 'manual_verdict': 'pass'}])
        self.assertEqual(source.read_bytes(), original)

    def test_audit_rejects_nonpositive_sample_size(self):
        with self.assertRaises(SystemExit) as error:
            self.cli(eval_answers, 'audit', '--n', 0, '--output', self.output)
        self.assertEqual(error.exception.code, 2)

    def test_dataset_default_matches_evaluator_and_generation_is_non_destructive(self):
        self.assertEqual(build_eval_set.DEFAULT_OUTPUT, eval_answers.EVAL_SET)
        self.cli(build_eval_set, '--output', self.output)
        original = self.output.read_bytes()
        generated = json.loads(original)
        self.assertEqual(len(generated['questions']), 74)
        self.assertEqual(generated['questions'], build_eval_set.QS)
        with self.assertRaises(SystemExit) as error:
            self.cli(build_eval_set, '--output', self.output)
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.output.read_bytes(), original)

    def test_benchmark_rejects_active_related_and_existing_directories(self):
        active = self.root / 'active'
        active.mkdir()
        sentinel = active / 'index.bin'
        sentinel.write_bytes(b'index data')
        previous = self.root / 'previous_benchmark'
        previous.mkdir()
        with patch.object(comparison, 'DB_PATH', active):
            for path in (active, active / 'nested', active / '..' / 'active', self.root, previous):
                with self.subTest(path=path):
                    with self.assertRaises((ValueError, FileExistsError)):
                        comparison.prepare_benchmark_directory(path)
        self.assertEqual(sentinel.read_bytes(), b'index data')
        self.assertEqual(list(active.iterdir()), [sentinel])

    def test_collection_collision_never_deletes_or_upserts(self):
        client = Mock()
        client.create_collection.side_effect = ValueError('already exists')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            comparison.create_candidate_collection(client, 'benchmark_bge', [{}], ['1'], [[1]])
        client.delete_collection.assert_not_called()
        client.get_or_create_collection.assert_not_called()

    def test_benchmark_only_opens_fresh_database_and_preserves_model_settings(self):
        active = self.root / 'active'
        active.mkdir()
        sentinel = active / 'chroma.sqlite3'
        sentinel.write_bytes(b'original index')
        database = self.root / 'benchmark'
        chunks = [{'chunk_id': 0, 'source_document': 'Law', 'article': 'Article 1',
                   'filename': 'law.pdf', 'text': 'fact'}]
        questions = [{'id': 'E1', 'question': 'test', 'answerable': True,
                      'expected_source_document': 'Law', 'expected_article': 'Article 1'}]
        client = Mock()
        def collection(**kwargs):
            result = Mock()
            result.name = kwargs['name']
            result.count.return_value = 1
            result.query.return_value = {'metadatas': [[chunks[0]]], 'distances': [[0.1]]}
            return result
        client.create_collection.side_effect = collection
        chroma = SimpleNamespace(PersistentClient=Mock(return_value=client))
        models = []
        def model_factory(name):
            model = Mock()
            model.encode.return_value.tolist.return_value = [[1.0]]
            models.append(model)
            return model
        transformers = SimpleNamespace(SentenceTransformer=Mock(side_effect=model_factory))
        with patch.dict(sys.modules, {'chromadb': chroma, 'sentence_transformers': transformers}), \
             patch.object(comparison, 'DB_PATH', active), \
             patch.object(comparison, 'load_json', side_effect=[chunks, questions]):
            self.cli(comparison, '--db-path', database, '--output', self.output)
        chroma.PersistentClient.assert_called_once_with(path=str(database.resolve()))
        client.delete_collection.assert_not_called()
        client.get_collection.assert_not_called()
        created = [call.kwargs for call in client.create_collection.call_args_list]
        self.assertEqual([c['name'] for c in created],
                         ['benchmark_minilm', 'benchmark_mpnet', 'benchmark_bge'])
        self.assertEqual([c['metadata']['hnsw:space'] for c in created], ['l2', 'cosine', 'cosine'])
        self.assertFalse(models[0].encode.call_args_list[0].kwargs['normalize_embeddings'])
        self.assertFalse(models[0].encode.call_args_list[1].kwargs['normalize_embeddings'])
        self.assertTrue(models[2].encode.call_args_list[0].kwargs['normalize_embeddings'])
        self.assertEqual(models[2].encode.call_args_list[1].args[0],
                         'Represent this sentence for searching relevant passages: test')
        report = json.loads(self.output.read_text())
        self.assertEqual(set(report['results']), {'MiniLM', 'MPNet', 'BGE'})
        self.assertEqual(sentinel.read_bytes(), b'original index')
        self.assertEqual(list(active.iterdir()), [sentinel])


if __name__ == '__main__':
    unittest.main()
