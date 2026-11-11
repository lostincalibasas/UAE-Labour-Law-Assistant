"""Synthetic fixtures only: these tests are NOT independent human validation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import independent_review as review
import independent_eval as evaluator
from regime_selector import GENERAL, DOMESTIC


def synthetic_judgment():
    return {'review_status': 'reviewed', 'applicable_legislation': [GENERAL],
            'supporting_articles': [{'source_document': GENERAL, 'article': 'Article 43',
                                     'necessary': True, 'availability': 'in_corpus', 'rationale': 'SYNTHETIC UNIT TEST'}],
            'answerability': 'answerable', 'permitted_filter': 'general', 'confidence': 'high',
            'explanation': 'SYNTHETIC UNIT TEST ONLY', 'source_basis': 'MOCK, NOT HUMAN REVIEW',
            'coverage_tags': ['general_employment']}


class ReviewImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet_path = self.root/'reviewer'/'packet.json'
        self.markdown_path = self.root/'reviewer'/'packet.md'
        self.manifest_path = self.root/'private'/'manifest.json'
        self.packet = review.prepare_packet(self.packet_path, self.markdown_path, self.manifest_path)
        self.manifest = review.load_json(self.manifest_path)

    def completed_fixture(self):
        packet = copy.deepcopy(self.packet)
        packet['reviewer'] = {'reviewer_id': 'UNIT_TEST_NOT_A_REVIEWER',
                              'expertise': 'Synthetic fixture, not evidence of human review', 'completed_at': '2026-11-11'}
        packet['attestations'] = {k: True for k in packet['attestations']}
        for case in packet['cases']:
            case['human_review'] = synthetic_judgment()
        return packet

    def test_packet_is_blinded_and_all_judgments_blank(self):
        self.assertEqual(len(self.packet['cases']), 32)
        self.assertEqual(set(self.packet), {'schema_version', 'packet_id', 'purpose', 'question_provenance', 'reviewer', 'attestations', 'cases'})
        for case in self.packet['cases']:
            self.assertEqual(set(case), {'id', 'question', 'question_origin', 'human_review'})
            self.assertTrue(all(v is None for v in case['human_review'].values()))
        content = self.markdown_path.read_text(encoding='utf-8')
        for forbidden in ('Hit@10', 'Q041', 'Q068', 'administrator_coverage_topic', 'candidate_rank', 'expected_policy'):
            self.assertNotIn(forbidden, content)
        self.assertEqual({c['administrator_coverage_topic'] for c in self.manifest['prepared_cases']}, set(review.DOMAINS))

    def test_private_manifest_cannot_be_in_reviewer_tree(self):
        with self.assertRaises(ValueError):
            review.prepare_packet(self.root/'other'/'packet.json', self.root/'other'/'packet.md', self.root/'other'/'private'/'manifest.json')

    def test_blank_packet_rejected_without_output_or_index_access(self):
        output = self.root/'import.json'
        with self.assertRaisesRegex(ValueError, 'reviewer identity'):
            review.import_review(self.packet_path, self.manifest_path, output)
        self.assertFalse(output.exists())
        with patch.object(evaluator, 'locked_snapshot') as lock:
            with self.assertRaises(ValueError): evaluator.run(self.packet_path, output)
            lock.assert_not_called()

    def test_full_synthetic_import_preserves_source(self):
        completed = self.completed_fixture()
        source = self.root/'completed.json'; source.write_text(json.dumps(completed))
        before = source.read_bytes(); blank_before = self.packet_path.read_bytes()
        result = review.import_review(source, self.manifest_path, self.root/'import.json')
        self.assertEqual(len(result['cases']), 32)
        self.assertEqual(result['status'], 'human_reviewed_import')
        self.assertIn('not independently authenticated', result['judgment_provenance'])
        review.validate_import(result)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(self.packet_path.read_bytes(), blank_before)

    def test_incomplete_or_unattested_reviews_rejected(self):
        mutations = [lambda p: p['attestations'].update(judgments_are_human_not_ai_generated=False),
                     lambda p: p['attestations'].update(not_seen_predictions_keys_or_rankings='yes'),
                     lambda p: p['cases'][0]['human_review'].update(review_status='unresolved'),
                     lambda p: p['cases'][0]['human_review'].update(confidence=None),
                     lambda p: p['cases'][0]['human_review'].update(explanation=''),
                     lambda p: p['cases'][0]['human_review'].update(supporting_articles=None)]
        for mutate in mutations:
            packet = self.completed_fixture(); mutate(packet)
            with self.assertRaises(ValueError): review.validate_submission(packet, self.manifest)

    def test_prepared_cases_cannot_be_edited_dropped_duplicated_or_relabelled_origin(self):
        mutations = [lambda p: p['cases'][0].update(question='Changed'),
                     lambda p: p['cases'][0].update(question_origin='reviewer_authored'),
                     lambda p: p['cases'].pop(),
                     lambda p: p['cases'].append(copy.deepcopy(p['cases'][0])),
                     lambda p: p['cases'][0].update(expected_policy='general')]
        for mutate in mutations:
            packet = self.completed_fixture(); mutate(packet)
            with self.assertRaises(ValueError): review.validate_submission(packet, self.manifest)

    def test_reviewer_authored_additions_allowed_with_explicit_provenance(self):
        packet = self.completed_fixture()
        packet['cases'].append({'id': 'H001', 'question': 'UNIT TEST QUESTION', 'question_origin': 'reviewer_authored',
                                'human_review': synthetic_judgment()})
        self.assertEqual(len(review.validate_submission(packet, self.manifest)), 33)

    def test_article_availability_necessity_and_law_consistency(self):
        for change in ({'necessary': 1}, {'availability': 'maybe'}, {'source_document': 'Undeclared law'}):
            packet = self.completed_fixture()
            packet['cases'][0]['human_review']['supporting_articles'][0].update(change)
            with self.assertRaises(ValueError): review.validate_submission(packet, self.manifest)
        packet = self.completed_fixture()
        packet['cases'][0]['human_review']['supporting_articles'] *= 2
        with self.assertRaises(ValueError): review.validate_submission(packet, self.manifest)

    def test_true_out_of_scope_case_can_have_no_expected_articles(self):
        packet = self.completed_fixture()
        packet['cases'][0]['human_review'].update(answerability='out_of_scope', applicable_legislation=[],
                                                 supporting_articles=[], permitted_filter='no_filter')
        review.validate_submission(packet, self.manifest)
        packet['cases'][0]['human_review']['permitted_filter'] = 'general'
        with self.assertRaises(ValueError): review.validate_submission(packet, self.manifest)

    def test_frozen_selector_and_criteria_cannot_be_changed_silently(self):
        for field in ('selector_sha256', 'retriever_sha256', 'corpus_sha256'):
            manifest = copy.deepcopy(self.manifest); manifest[field] = 'changed'
            with self.assertRaises(ValueError): review.validate_frozen_inputs(manifest)
        manifest = copy.deepcopy(self.manifest); manifest['criteria']['maximum_harmful_exclusion_cases'] = 1
        with self.assertRaises(ValueError): review.validate_frozen_inputs(manifest)

    def test_nonoverwrite_and_strict_json(self):
        before = self.packet_path.read_bytes()
        with self.assertRaises(FileExistsError): review.prepare_packet(self.packet_path, self.markdown_path, self.manifest_path)
        self.assertEqual(before, self.packet_path.read_bytes())
        for data in ('{"cases":[],"cases":[]}', '{"confidence":NaN}'):
            path = self.root/'bad.json'; path.write_text(data)
            with self.assertRaises(ValueError): review.load_json(path)


class IndependentScoringTests(unittest.TestCase):
    def chunks(self):
        return [{'chunk_id': '1', 'source_document': GENERAL, 'article': 'Article 43', 'text': 'Mock general evidence', 'distance': .1},
                {'chunk_id': '2', 'source_document': DOMESTIC[0], 'article': 'Article 10', 'text': 'Mock domestic evidence', 'distance': .2}]

    def row(self, proposed=None, needed_domestic=False):
        chunks = self.chunks(); human = synthetic_judgment()
        if needed_domestic:
            human['applicable_legislation'].append(DOMESTIC[0])
            human['supporting_articles'].append({'source_document': DOMESTIC[0], 'article': 'Article 10', 'necessary': True,
                                                'availability': 'in_corpus', 'rationale': 'SYNTHETIC NECESSARY EVIDENCE'})
            human['permitted_filter'] = 'no_filter'
        pair = {'baseline': chunks, 'experimental': chunks if proposed is None else proposed,
                'selection': {'regime': 'general', 'sources': [GENERAL], 'where': {'source_document': {'$in': [GENERAL]}}},
                'baseline_ms': 1, 'experimental_ms': 1.1, 'selection_ms': .01}
        case = {'id': 'V001', 'question_origin': 'assistant_prepared', 'human_review': human}
        return evaluator.score(case, pair, 10)

    def test_necessary_exclusion_detected_even_when_an_expected_article_is_hit(self):
        row = self.row([self.chunks()[0]], needed_domestic=True)
        self.assertEqual(row['arms']['experimental']['metrics']['10']['hit'], 1)
        self.assertTrue(row['necessary_source_exclusions'])
        self.assertTrue(row['observed_necessary_evidence_losses'])
        self.assertTrue(row['incorrect_forced_filter'])
        result = evaluator.assessment([row])
        self.assertFalse(result['automated_gates']['no_harmful_necessary_evidence_exclusion'])
        self.assertFalse(result['production_approved'])

    def test_source_exclusion_detected_even_if_baseline_already_missed_article(self):
        row = self.row(needed_domestic=True)
        self.assertTrue(row['necessary_source_exclusions'])
        self.assertFalse(row['observed_necessary_evidence_losses'])

    def test_no_data_never_passes_and_zero_denominators_are_not_accuracy(self):
        result = evaluator.assessment([])
        self.assertEqual(result['status'], 'not_ready')
        self.assertIsNone(result['metrics']['experimental']['10']['hit'])
        self.assertFalse(result['automated_gates']['minimum_scored_cases'])

    def test_ranking_regression_is_visible_even_if_hit10_unchanged(self):
        chunks = self.chunks()
        row = self.row(list(reversed(chunks)))
        report = evaluator.assessment([row])
        self.assertEqual(row['arms']['experimental']['metrics']['10']['hit'], 1)
        self.assertEqual(report['regressions']['1']['hit'], ['V001'])
        self.assertEqual(report['regressions']['10']['rr'], ['V001'])

    def test_low_confidence_and_uncertain_article_availability_block_readiness(self):
        row = self.row(); row['review_confidence'] = 'low'
        self.assertFalse(evaluator.assessment([row])['automated_gates']['no_low_confidence_or_uncertain_availability'])
        row = self.row(); row['human_judgment']['supporting_articles'][0]['availability'] = 'uncertain'
        self.assertFalse(evaluator.assessment([row])['automated_gates']['no_low_confidence_or_uncertain_availability'])

    def test_uncertainty_preserves_exact_baseline_and_runtime_has_no_labels(self):
        chunks = self.chunks()
        with patch('phase42_eval.dense_query', return_value=chunks) as query:
            result = evaluator.retrieve_pair('What rules cover this employee?', [GENERAL, DOMESTIC[0]], Mock(), [1.])
        self.assertIs(result['baseline'], result['experimental'])
        self.assertEqual(query.call_count, 1)
        with self.assertRaises(TypeError):
            evaluator.retrieve_pair('question', [GENERAL], Mock(), [1.], expected_articles=[])

    def test_latency_and_provenance_coverage_are_gates(self):
        row = self.row(); row['arms']['experimental']['total_ms'] = 9999
        report = evaluator.assessment([row])
        self.assertFalse(report['automated_gates']['median_latency'])
        self.assertFalse(report['automated_gates']['reviewer_authored_case_count'])
        self.assertFalse(report['automated_gates']['necessary_evidence_coverage'])

    def test_protected_output_refused_before_any_index(self):
        from index_paths import PROTECTED_INDEX
        with patch.object(evaluator, 'locked_snapshot') as lock:
            with self.assertRaises(ValueError): evaluator.run('unused.json', PROTECTED_INDEX/'new.json')
            lock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
