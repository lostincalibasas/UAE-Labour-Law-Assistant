"""Offline evaluator reliability and experimental retrieval regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import eval_judge
import retrieval_experiments as experiment
from evidence_citations import build_evidence, FALLBACK
from test_phase4 import Q, CHUNKS, judgment


class DiagnosticTests(unittest.TestCase):
    def grade(self, value, answer='True [E1].'):
        return eval_judge.evaluate(Q, answer, build_evidence(CHUNKS), Mock(return_value=value))

    def test_exact_field_paths_and_multiple_violations(self):
        value = judgment()
        value['facts'][0]['evidence_ids'] = ['E99']
        value['claims'][0]['quote'] = 'Reworded [E1].'
        value['forbidden'][0]['triggered'] = 'false'
        result = self.grade(value)
        issues = {(i['path'], i['code']) for i in result['diagnostics']}
        self.assertIn(('$.facts[0].evidence_ids', 'unknown_evidence_id'), issues)
        self.assertIn(('$.claims[0].quote', 'quote_not_exact_answer_span'), issues)
        self.assertIn(('$.forbidden[0].triggered', 'expected_boolean'), issues)
        self.assertFalse(result['scores']['pass'])
        self.assertEqual(result['validator_version'], 2)

    def test_missing_fact_and_forbidden_rows_never_pass(self):
        value = judgment(); value['facts'] = []; value['forbidden'] = []
        result = self.grade(value)
        self.assertEqual(result['status'], 'evaluation_failure')
        self.assertIn({'path': '$.facts', 'code': 'row_count_mismatch'}, result['diagnostics'])
        self.assertIn({'path': '$.forbidden', 'code': 'incomplete_or_duplicate_ids'}, result['diagnostics'])

    def test_duplicate_id_and_bool_id_diagnosed(self):
        value = judgment(); value['facts'][0]['id'] = True
        result = self.grade(value)
        self.assertIn({'path': '$.facts', 'code': 'expected_integer_row_ids'}, result['diagnostics'])
        value = judgment(); value['facts'] *= 2
        result = self.grade(value)
        self.assertIn({'path': '$.facts', 'code': 'incomplete_or_duplicate_ids'}, result['diagnostics'])

    def test_missing_field_and_unsafe_extra_key_not_echoed(self):
        value = judgment(); value['SECRET_CREDENTIAL'] = 'SECRET_CREDENTIAL'
        del value['facts'][0]['reason']
        result = self.grade(value)
        self.assertNotIn('SECRET_CREDENTIAL', json.dumps(result))
        self.assertIn({'path': '$', 'code': 'unexpected_fields'}, result['diagnostics'])
        self.assertIn({'path': '$.facts[0].reason', 'code': 'required_field_missing'}, result['diagnostics'])

    def test_syntax_errors_fingerprinted_without_raw_payload(self):
        for raw, code in [('SECRET_NOT_JSON', 'invalid_json'),
                          ('{"SECRET":1,"SECRET":2}', 'duplicate_json_key'),
                          ('{"value":NaN}', 'nonfinite_json_number'),
                          ('```json\n{}\n```', 'invalid_json')]:
            with self.subTest(code=code):
                result = eval_judge.evaluate(Q, 'True [E1].', build_evidence(CHUNKS), lambda _: eval_judge.parse_response(raw))
                self.assertEqual(result['diagnostics'][0]['code'], code)
                self.assertEqual(len(result['response_summary']['sha256']), 64)
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertFalse(result['scores']['pass'])

    def test_claim_citation_mapping_and_supported_uncited_claim(self):
        value = judgment(); value['claims'][0]['evidence_ids'] = []
        result = self.grade(value)
        self.assertIn({'path': '$.claims[0].evidence_ids', 'code': 'citation_mapping_mismatch'}, result['diagnostics'])
        value = judgment(); value['claims'][0].update(quote='True', evidence_ids=[])
        result = self.grade(value)
        self.assertIn({'path': '$.claims[0].verdict', 'code': 'supported_claim_without_citation'}, result['diagnostics'])

    def test_wrong_law_support_conflict_diagnosed(self):
        value = judgment(); value['claims'][0]['wrong_law'] = True
        result = self.grade(value)
        self.assertIn({'path': '$.claims[0].verdict', 'code': 'supported_claim_wrong_law_conflict'}, result['diagnostics'])

    def test_prompt_has_exact_contract_and_fallback_rules(self):
        caller = Mock(return_value=judgment())
        eval_judge.evaluate(Q, 'True [E1].', build_evidence(CHUNKS), caller)
        prompt = caller.call_args.args[0]
        payload = json.loads(prompt.split('INPUT JSON:\n')[1])
        self.assertEqual(payload['response_contract']['fact_ids'], [0])
        self.assertEqual(payload['response_contract']['allowed_evidence_ids'], ['E1'])
        self.assertIn('Copy claim quote spans verbatim', prompt)
        self.assertIn('correct safe response', prompt)

    def test_valid_result_and_input_unchanged(self):
        value = judgment(); before = copy.deepcopy(value)
        # validate itself has no mutation or automatic repair.
        eval_judge.validate(value, Q, 'True [E1].', build_evidence(CHUNKS))
        self.assertEqual(value, before)
        self.assertTrue(self.grade(value)['scores']['pass'])

    def test_historical_failures_not_reclassified(self):
        path = Path(__file__).resolve().parents[1] / 'runs/phase4-live-pilot-01.json'
        if not path.exists():
            self.skipTest('Local pilot artifact unavailable')
        before = path.read_bytes()
        rows = json.loads(before)['rows']
        for row in rows:
            if row['id'] in {'Q044', 'Q049', 'Q073'}:
                self.assertEqual(row['judge']['error'], 'judge_schema_invalid')
                self.assertNotIn('diagnostics', row['judge'])
                self.assertFalse(row['judge']['scores']['pass'])
        self.assertEqual(path.read_bytes(), before)

    def test_abstention_inconsistent_grading_rejected_without_repair(self):
        value = judgment(); value.update(claims=[], evidence_sufficient=False, answer_correct=False)
        original = copy.deepcopy(value)
        result = self.grade(value, FALLBACK)
        self.assertIn({'path': '$.answer_correct', 'code': 'abstention_correctness_conflict'}, result['diagnostics'])
        self.assertEqual(value, original)
        value['answer_correct'] = True
        self.assertEqual(self.grade(value, FALLBACK)['status'], 'valid')

    def test_manual_worksheet_preserves_historical_artifact_and_pending_verdicts(self):
        from eval_review import create_worksheet, REVIEW_IDS
        root = Path(__file__).resolve().parents[1]
        source = root / 'runs/phase4-live-pilot-01.json'
        if not source.exists(): self.skipTest('Local pilot artifact unavailable')
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output, md = Path(directory) / 'review.json', Path(directory) / 'review.md'
            result = create_worksheet(source, root / 'data/eval_set.json', output, md)
            self.assertEqual([i['id'] for i in result['items']], list(REVIEW_IDS))
            self.assertTrue(all(i['human_review']['verdict'] is None for i in result['items']))
            for item in result['items'][:3]:
                self.assertFalse(item['automated_snapshot']['judge']['scores']['pass'])
            saved = output.read_bytes()
            with self.assertRaises(FileExistsError): create_worksheet(source, root / 'data/eval_set.json', output, md)
            self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(source.read_bytes(), before)


class RetrievalExperimentTests(unittest.TestCase):
    def chunks(self):
        return [dict(chunk_id=str(i), text=text, source_document=source, article='Article 1', distance=.1+i*.01)
                for i, (source, text) in enumerate([
                    (experiment.DOMESTIC[0], 'domestic worker notice'),
                    (experiment.GENERAL, 'private sector recruitment fees'),
                    (experiment.DOMESTIC[1], 'recruitment office fees')])]

    def test_question_only_routing_and_scope_precedence(self):
        self.assertEqual(experiment.route('Does the main labour law apply to domestic workers?'), 'general')
        self.assertEqual(experiment.route('Private-sector recruitment fees?'), 'general')
        self.assertEqual(experiment.route('Domestic worker notice?'), 'domestic')
        self.assertEqual(experiment.route('Employee notice?'), 'unspecified')

    def test_metadata_filter_is_exact_and_preserves_order(self):
        chunks = self.chunks(); before = copy.deepcopy(chunks)
        self.assertEqual(experiment.filter_candidates(chunks, 'general'), [chunks[1]])
        self.assertEqual(experiment.filter_candidates(chunks, 'domestic'), [chunks[0], chunks[2]])
        self.assertEqual(experiment.filter_candidates(chunks, 'unspecified'), chunks)
        self.assertEqual(chunks, before)

    def test_rerank_preserves_candidate_membership_and_is_deterministic(self):
        chunks = self.chunks(); before = copy.deepcopy(chunks)
        reranker = experiment.LexicalReranker(chunks)
        first = reranker.rerank('recruitment fees', chunks)
        second = reranker.rerank('recruitment fees', chunks)
        self.assertEqual(first, second)
        self.assertEqual({c['chunk_id'] for c in first}, {c['chunk_id'] for c in chunks})
        self.assertEqual(chunks, before)
        self.assertEqual(reranker.rerank('zzzz', chunks), chunks)

    def test_prefilter_query_uses_existing_vectors_and_no_mutation(self):
        collection = Mock()
        collection.count.return_value = 3
        collection.query.return_value = {'ids': [['1']], 'documents': [['fact']],
            'metadatas': [[{'source_document': experiment.GENERAL, 'article': 'Article 1'}]], 'distances': [[.1]]}
        result = experiment.query(collection, [1., 0.], 50, 'general')
        kwargs = collection.query.call_args.kwargs
        self.assertEqual(kwargs['query_embeddings'], [[1., 0.]])
        self.assertEqual(kwargs['where'], {'source_document': {'$in': [experiment.GENERAL]}})
        self.assertEqual(kwargs['n_results'], 3)
        self.assertEqual(result[0]['chunk_id'], '1')
        collection.add.assert_not_called(); collection.upsert.assert_not_called(); collection.delete.assert_not_called()

    def test_empty_index_never_queries_zero(self):
        collection = Mock(); collection.count.return_value = 0
        with self.assertRaises(ValueError): experiment.query(collection, [1.], 10)
        collection.query.assert_not_called()

    def test_output_and_original_worker_refused(self):
        from index_paths import PROTECTED_INDEX
        with patch.object(experiment, 'locked_snapshot') as lock:
            with self.assertRaises(ValueError): experiment.run(PROTECTED_INDEX / 'new-result.json')
            lock.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'existing.json'; output.write_bytes(b'preserve')
            with patch.object(experiment, 'locked_snapshot') as lock:
                with self.assertRaises(FileExistsError): experiment.run(output)
                lock.assert_not_called()
            self.assertEqual(output.read_bytes(), b'preserve')

    def test_exact_cosine_ranks_known_vectors(self):
        chunks = self.chunks()
        ranked = experiment.exact_ranks([1., 0.], chunks, [[0., 1.], [1., 0.], [-1., 0.]])
        self.assertEqual([c['chunk_id'] for c in ranked], ['1', '0', '2'])
        self.assertAlmostEqual(ranked[0]['distance'], 0)

    def test_regression_reporting_detects_loss(self):
        expected = [{'source_document': experiment.GENERAL, 'article': 'Article 1'}]
        chunks = self.chunks()
        baseline = {'metrics': experiment.metrics(chunks, expected), 'retrieval_ms': 1}
        failed = {'metrics': experiment.metrics([chunks[0]], expected), 'retrieval_ms': 2}
        rows = [{'id': 'Q001', 'encode_ms': 1, 'variants': {'baseline10': baseline, 'failed': failed}}]
        summary = experiment.compare(rows)
        self.assertEqual(summary['failed']['hit_regressions_at_10'], ['Q001'])
        self.assertEqual(summary['failed']['recall_regressions_at_10'], ['Q001'])

    def test_scoped_replay_never_opens_index_and_preserves_input(self):
        rows = []
        expected = [{'source_document': experiment.GENERAL, 'article': 'Article 1'}]
        chunks = self.chunks()
        baseline = {'metrics': experiment.metrics(chunks, expected), 'retrieval_ms': 1}
        other = {'metrics': experiment.metrics([chunks[0]], expected), 'retrieval_ms': 2}
        for identifier, regime in [('A', 'unspecified'), ('B', 'general')]:
            rows.append({'id': identifier, 'regime': regime, 'encode_ms': 1,
                         'variants': {'baseline10': baseline, 'prefilter_rrf50_top10': other}})
        source = {'rows': rows, 'status': 'completed', 'original_hashes_unchanged': True,
                  'isolation': {'logical_differences': {}, 'reopen_differences': {}}}
        with tempfile.TemporaryDirectory() as directory:
            input_path, output = Path(directory) / 'source.json', Path(directory) / 'replay.json'
            input_path.write_text(json.dumps(source)); before = input_path.read_bytes()
            with patch.object(experiment, 'install_chroma_guard') as guard, patch.object(experiment, 'run') as run:
                result = experiment.replay_scoped(input_path, output)
                guard.assert_not_called(); run.assert_not_called()
            a, b = result['rows']
            self.assertEqual(a['variants']['scoped_prefilter_rrf50_top10'], a['variants']['baseline10'])
            self.assertEqual(b['variants']['scoped_prefilter_rrf50_top10'], b['variants']['prefilter_rrf50_top10'])
            self.assertEqual(input_path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
