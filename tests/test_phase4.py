"""Phase 4 regressions; mocked providers and temporary artifacts only."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import eval_answers
import eval_judge
import phase4_eval as runner
from eval_report import classify, make_report
from evidence_citations import build_evidence, resolve_answer, FALLBACK
from index_integrity import digest
from index_paths import PROTECTED_INDEX

CHUNKS = [{'text': 'The fact is true.', 'source_document': 'Law A', 'article': 'Article 1', 'distance': .1}]
Q = {'id': 'Q001', 'question': 'Fact?', 'category': 'single_fact', 'answerable': True,
     'expected_articles': [{'source_document': 'Law A', 'article': 'Article 1'}],
     'must_include': [{'fact': 'The fact is true.'}], 'must_not_include': ['Wrong fact'], 'must_not_cite': []}
CONFIG = {'mode': 'answers', 'ids': ['Q001'], 'ks': [1, 10], 'answer_k': 10,
          'generation_budget': 1, 'judge_budget': 1, 'no_judge': False, 'diagnostics': False}


def judgment():
    return {'facts': [{'id': 0, 'verdict': 'present', 'evidence_ids': ['E1'], 'reason': 'Matches'}],
            'forbidden': [{'id': 0, 'triggered': False, 'reason': 'Absent'}],
            'claims': [{'id': 0, 'quote': 'True [E1].', 'evidence_ids': ['E1'],
                        'verdict': 'supported', 'wrong_law': False, 'reason': 'Supported'}],
            'unsupported_claims': [], 'evidence_sufficient': True, 'answer_correct': True}


class JudgeTests(unittest.TestCase):
    def grade(self, result):
        return eval_judge.evaluate(Q, 'True [E1].', build_evidence(CHUNKS), Mock(return_value=result))

    def test_valid_and_exact_evidence_prompt(self):
        caller = Mock(return_value=judgment())
        result = eval_judge.evaluate(Q, 'True [E1].', build_evidence(CHUNKS), caller)
        self.assertTrue(result['scores']['pass'])
        payload = json.loads(caller.call_args.args[0].split('INPUT JSON:\n')[1])
        self.assertEqual(payload['evidence'], build_evidence(CHUNKS))

    def test_malformed_or_incomplete_never_passes(self):
        bad = [None, [], {}, {'facts': []}]
        for field in judgment():
            item = judgment(); del item[field]; bad.append(item)
        for field, value in [('facts', []), ('forbidden', []), ('claims', []),
                             ('evidence_sufficient', 'true'), ('answer_correct', 1),
                             ('unsupported_claims', 'none')]:
            item = judgment(); item[field] = value; bad.append(item)
        for field, value in [('id', True), ('id', 1), ('verdict', 'maybe'), ('evidence_ids', ['E9'])]:
            item = judgment(); item['facts'][0][field] = value; bad.append(item)
        item = judgment(); item['facts'] *= 2; bad.append(item)
        for field, value in [('quote', 'Invented span'), ('evidence_ids', []), ('evidence_ids', ['E2']),
                             ('wrong_law', 'false'), ('verdict', 'yes')]:
            item = judgment(); item['claims'][0][field] = value; bad.append(item)
        for value in bad:
            with self.subTest(value=value):
                result = self.grade(value)
                self.assertEqual(result['status'], 'evaluation_failure')
                self.assertFalse(result['scores']['pass'])

    def test_unsupported_contradiction_wrong_law_prevent_pass(self):
        for verdict, wrong in [('unsupported', False), ('contradicted', False), ('unsupported', True)]:
            item = judgment(); item['claims'][0].update(verdict=verdict, wrong_law=wrong)
            self.assertFalse(self.grade(item)['scores']['pass'])
        item = judgment(); item['unsupported_claims'] = ['Extra invented claim']
        self.assertFalse(self.grade(item)['scores']['pass'])

    def test_errors_do_not_persist_secret(self):
        result = eval_judge.evaluate(Q, 'answer', [], Mock(side_effect=RuntimeError('SECRET')))
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['status'], 'evaluation_failure')

    def test_json_parser_rejects_wrappers_and_truncated(self):
        from types import SimpleNamespace as NS
        client = Mock()
        client.__enter__ = Mock(return_value=client); client.__exit__ = Mock(return_value=False)
        for finish, content in [('length', '{}'), ('stop', '```json\n{}\n```'), ('stop', '{"facts":[],"facts":[]}')]:
            client.chat.completions.create.return_value = NS(choices=[NS(finish_reason=finish, message=NS(role='assistant', content=content))])
            with patch('openai.OpenAI', return_value=client), patch.dict('os.environ', {'JUDGE_API_KEY': 'mock', 'JUDGE_MODEL': 'mock'}):
                with self.assertRaises(Exception):
                    eval_answers.call_judge('mock')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def run_cases(self, config=None, questions=None, generate=None, judge=None):
        retrieve = Mock(return_value=copy.deepcopy(CHUNKS))
        def generator(_q, _k, **kwargs):
            kwargs['before_request']()
            return resolve_answer('True [E1].', kwargs['evidence'])
        def grade(q, a, e, **kwargs):
            kwargs['before_request']()
            return eval_judge.evaluate(q, a, e, Mock(return_value=judgment()))
        judge = judge or Mock(side_effect=grade)
        result = runner.evaluate_questions(questions or [Q], config or CONFIG, retrieve, generate or generator, judge)
        return result, retrieve, judge

    def test_single_retrieval_shared_evidence(self):
        captured = []
        def generator(_q, _k, **kw):
            kw['before_request'](); captured.append(kw['evidence'])
            return resolve_answer('True [E1].', kw['evidence'])
        result, retrieve, judge = self.run_cases(generate=generator)
        retrieve.assert_called_once_with('Fact?', top_k=10)
        self.assertIs(captured[0], judge.call_args.args[2])
        row = result['rows'][0]
        self.assertEqual(digest(captured[0]), row['evidence_sha256'])
        self.assertEqual(row['response']['citations'][0]['excerpt'], CHUNKS[0]['text'])
        self.assertEqual(result['requests'], {'generation': 1, 'judge': 1})

    def test_generator_with_captured_evidence_never_retrieves(self):
        import generate_answer
        from types import SimpleNamespace as NS
        from unittest.mock import MagicMock
        client = MagicMock(); client.__enter__.return_value = client
        client.chat.completions.create.return_value = NS(choices=[NS(finish_reason='stop', message=NS(role='assistant', content='True [E1].'))])
        with patch.object(generate_answer, 'retrieve_chunks') as retrieve, patch.object(generate_answer, 'get_api_client', return_value=client):
            result = generate_answer.generate_answer('Fact?', evidence=build_evidence(CHUNKS))
        retrieve.assert_not_called()
        self.assertEqual(result['status'], 'ok')

    def test_zero_budget_never_invokes_providers(self):
        generate, judge = Mock(), Mock()
        config = dict(CONFIG, generation_budget=0, judge_budget=0)
        result, _, _ = self.run_cases(config=config, generate=generate, judge=judge)
        generate.assert_not_called(); judge.assert_not_called()
        self.assertEqual(result['requests'], {'generation': 0, 'judge': 0})

    def test_separate_limits_and_exhaustion(self):
        questions = [dict(Q, id=f'Q{i:03}') for i in range(3)]
        result, retrieve, judge = self.run_cases(questions=questions, config=dict(CONFIG, generation_budget=2, judge_budget=1))
        self.assertEqual(retrieve.call_count, 3); self.assertEqual(judge.call_count, 1)
        self.assertEqual(result['requests'], {'generation': 2, 'judge': 1})
        budget = runner.Budget(0)
        with self.assertRaises(RuntimeError): budget.consume()

    def test_empty_evidence_does_not_call_generation_api(self):
        import generate_answer
        with patch.object(generate_answer, 'get_api_client') as api:
            response = generate_answer.generate_answer('test', evidence=[], before_request=runner.Budget(0).consume)
        api.assert_not_called(); self.assertEqual(response['status'], 'insufficient_evidence')

    def test_dry_run_no_index_or_api_and_output_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'plan.json'
            with patch.object(runner, 'run') as run, patch.object(runner, 'fingerprint_files', return_value={}):
                runner.main(['answers', '--ids', 'Q001', '--dry-run', '--output', str(output)])
                run.assert_not_called()
                before = output.read_bytes()
                with self.assertRaises(SystemExit):
                    runner.main(['answers', '--ids', 'Q001', '--dry-run', '--output', str(output)])
                self.assertEqual(before, output.read_bytes())

    def test_ids_explicit_unique_reproducible(self):
        qs = [dict(Q, id='A'), dict(Q, id='B')]
        self.assertEqual([q['id'] for q in runner.select_questions(qs, ['B', 'A'])], ['B', 'A'])
        for ids in (None, [], ['C'], ['A', 'A']):
            with self.assertRaises(ValueError): runner.select_questions(qs, ids)
        self.assertEqual(digest({'a': 1, 'b': 2}), digest({'b': 2, 'a': 1}))
        self.assertNotEqual(digest(CHUNKS), digest([]))

    def test_refuses_original_worker_and_output_before_chroma(self):
        with patch.object(runner, 'install_chroma_guard') as guard:
            with self.assertRaises(Exception): runner.worker(PROTECTED_INDEX)
            guard.assert_not_called()
        with patch.object(runner, 'locked_snapshot') as snapshot:
            with self.assertRaises(ValueError): runner.run(CONFIG, PROTECTED_INDEX / 'new-report.json')
            snapshot.assert_not_called()

    def test_worker_rejects_copy_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'working').mkdir()
            (root / 'config.json').write_text(json.dumps(CONFIG))
            (root / 'source-baseline.json').write_text(json.dumps({'source': str(PROTECTED_INDEX), 'hashes': {'missing': 'x'}}))
            with patch.object(runner, 'install_chroma_guard') as guard:
                with self.assertRaises(RuntimeError): runner.worker(root)
                guard.assert_not_called()

    def test_classification_and_denominators(self):
        result, _, _ = self.run_cases()
        row = result['rows'][0]
        self.assertEqual(classify(row), 'automated_pass')
        row['response'] = resolve_answer(FALLBACK, build_evidence(CHUNKS))
        self.assertEqual(classify(row), 'unnecessary_abstention')
        row['judge']['evidence_sufficient'] = False
        self.assertEqual(classify(row), 'evidence_limited_abstention')
        row['answerable'] = False
        self.assertEqual(classify(row), 'legitimate_abstention')
        row['response']['citation_validation']['status'] = 'invalid_citations'
        self.assertEqual(classify(row), 'citation_rejection')
        row['response']['status'] = 'operational_error'
        self.assertEqual(classify(row), 'generation_operational_failure')
        row['retrieval_error'] = 'index_missing'
        self.assertEqual(classify(row), 'retrieval_operational_failure')
        offline, _, _ = self.run_cases(config=dict(CONFIG, mode='retrieval', generation_budget=0, judge_budget=0))
        offline['config'] = CONFIG
        report = make_report(offline)
        self.assertEqual(report['metrics']['answer_correctness']['denominator'], 0)
        self.assertIsNone(report['metrics']['answer_correctness']['value'])
        self.assertEqual(report['retrieval']['10']['hit'], 1)

    def test_diagnostics_detect_split_quote_and_review_flag(self):
        q = dict(Q, id='Q041', must_include=[{'fact': 'abc', 'quote': 'abcdef', 'source_document': 'Law A', 'article': 'Article 1'}])
        stored = [dict(CHUNKS[0], text='abc', chunk_id=1), dict(CHUNKS[0], text='def', chunk_id=2)]
        result = runner.diagnose(q, CHUNKS, stored)
        self.assertTrue(result['human_answer_key_review'])
        check = result['quote_boundary_checks'][0]
        self.assertFalse(check['single_chunk_ids'])
        self.assertTrue(check['reconstructed_article_contains_quote'])

    def test_legacy_evaluation_cannot_open_original(self):
        import evaluate
        with patch('index_isolation._guarded_path', None), patch('retrieve_bge.get_collection') as collection:
            with self.assertRaises(Exception): evaluate.retrieve_chunks('test')
            collection.assert_not_called()

    def test_mutated_evidence_cannot_be_scored(self):
        def generator(_q, _k, **kw):
            kw['evidence'][0]['text'] = 'tampered'
            return resolve_answer('True [E1].', kw['evidence'])
        with self.assertRaisesRegex(RuntimeError, 'Captured evidence changed'):
            self.run_cases(generate=generator)

    def test_forged_citation_metadata_rejected_before_judge(self):
        def generator(_q, _k, **kw):
            kw['before_request']()
            response = resolve_answer('True [E1].', kw['evidence'])
            response['citations'][0]['source_document'] = 'Wrong law'
            return response
        judge = Mock()
        result, _, _ = self.run_cases(generate=generator, judge=judge)
        judge.assert_not_called()
        self.assertEqual(classify(result['rows'][0]), 'citation_rejection')

    def test_parent_verifies_original_hashes_and_never_overwrites(self):
        from types import SimpleNamespace as NS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace = root / 'workspace'; workspace.mkdir()
            output = root / 'result.json'
            with patch.object(runner.tempfile, 'mkdtemp', return_value=str(workspace)), \
                 patch.object(runner, 'locked_snapshot') as lock, \
                 patch.object(runner.subprocess, 'run', return_value=NS(returncode=2)):
                snapshot = lock.return_value.__enter__.return_value
                snapshot.hashes.side_effect = [{'original': 'same'}, {'original': 'same'}]
                result = runner.run(CONFIG, output)
                self.assertTrue(result['original_hashes_unchanged'])
                self.assertEqual(result['status'], 'blocked')
                snapshot.copy_to.assert_called_once_with(workspace / 'working')
                before = output.read_bytes()
                with self.assertRaises(FileExistsError): runner.run(CONFIG, output)
                self.assertEqual(before, output.read_bytes())

    def test_final_hash_change_never_reports_success(self):
        from types import SimpleNamespace as NS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace = root / 'workspace'; workspace.mkdir()
            with patch.object(runner.tempfile, 'mkdtemp', return_value=str(workspace)), \
                 patch.object(runner, 'locked_snapshot') as lock, \
                 patch.object(runner.subprocess, 'run', return_value=NS(returncode=2)):
                snapshot = lock.return_value.__enter__.return_value
                snapshot.hashes.side_effect = [{'original': 'before'}, {'original': 'after'}]
                result = runner.run(CONFIG, root / 'result.json')
                self.assertFalse(result['original_hashes_unchanged'])
                self.assertEqual(result['status'], 'integrity_failure')

    def test_invalid_judge_classified_and_excluded_from_quality_denominator(self):
        result, _, _ = self.run_cases()
        row = result['rows'][0]
        row['judge'] = {'status': 'evaluation_failure', 'scores': {'pass': False}}
        self.assertEqual(classify(row), 'evaluation_failure')
        result['config'] = CONFIG
        report = make_report(result)
        self.assertEqual(report['metrics']['judge_failure_rate']['value'], 1)
        self.assertIsNone(report['metrics']['answer_correctness']['value'])

    def test_phase4_audit_verdict_is_separate_from_automatic_result(self):
        from types import SimpleNamespace as NS
        result, _, _ = self.run_cases()
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.json', Path(directory) / 'audit.json'
            source.write_text(json.dumps(result))
            before = source.read_bytes()
            with patch.object(eval_answers, 'load_eval_set', return_value=[Q]), patch('builtins.input', return_value='n'):
                eval_answers.cmd_audit(NS(input=source, output=output, seed=0, n=10))
            verdict = json.loads(output.read_text())[0]
            self.assertEqual(verdict['manual_verdict'], 'fail')
            self.assertTrue(verdict['judge_pass'])
            self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
