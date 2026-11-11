"""Blind packet preparation, strict human-review import, and readiness criteria.

No routing predictions, retrieval, model initialization or API calls in this module.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import uuid

from artifact_io import require_new_output, write_new_json
from index_integrity import digest
from index_paths import disjoint

BASE = Path(__file__).resolve().parent
DOMAINS = ('general_employment', 'domestic_workers', 'explicit_law', 'ambiguous_mixed',
           'negated_contradictory', 'unanswerable_out_of_scope')
CRITERIA = {
    'minimum_total_cases': 42, 'minimum_reviewer_authored_cases': 10,
    'minimum_cases_per_domain': 4, 'minimum_article_scored_cases': 24,
    'minimum_necessary_evidence_cases': 20, 'minimum_filtered_cases': 10,
    'minimum_filter_policy_cases_per_regime': 4, 'minimum_no_filter_cases': 8,
    'maximum_harmful_exclusion_cases': 0, 'maximum_incorrect_forced_filters': 0,
    'maximum_per_case_hit_recall_rr_regressions': 0,
    'minimum_confidence': 'medium', 'median_latency_ratio_limit': 1.25,
    'p95_latency_ratio_limit': 1.50, 'latency_allowance_ms': 5,
    'all_prepared_cases_required': True, 'human_attestation_required': True,
    'no_low_confidence_or_unresolved_evidence': True,
    'automatic_production_promotion': False,
    'separate_key_review_and_manual_signoff_required': True,
}


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError('Nonfinite JSON value')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=nonfinite)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def blank_judgment():
    return {key: None for key in ('review_status', 'applicable_legislation', 'supporting_articles',
                                 'answerability', 'permitted_filter', 'confidence', 'explanation',
                                 'source_basis', 'coverage_tags')}


def prepare_packet(packet_path, markdown_path, manifest_path):
    paths = [require_new_output(p) for p in (packet_path, markdown_path, manifest_path)]
    check(len({p.resolve() for p in paths}) == 3, 'Destinations must be distinct')
    check(all(disjoint(p) for p in paths), 'Destinations must be outside protected index storage')
    # The administrator manifest must never be in the reviewer delivery directory.
    check(disjoint(paths[2], paths[0].parent) and disjoint(paths[2], paths[1].parent),
          'Keep the private manifest outside the reviewer folder')
    from review_seed_questions import SEEDS
    prepared = [(domain, question) for domain, questions in SEEDS.items() for question in questions]
    random.SystemRandom().shuffle(prepared)
    packet = {
        'schema_version': 1, 'packet_id': str(uuid.uuid4()),
        'purpose': 'Independent human assessment; no machine predictions or answer labels are supplied.',
        'question_provenance': 'Prepared prompts are assistant-authored, not independent human judgments. Add at least ten independently authored questions using H001 etc.',
        'reviewer': {'reviewer_id': None, 'expertise': None, 'completed_at': None},
        'attestations': {'independent_of_selector_development': None,
                         'not_seen_predictions_keys_or_rankings': None,
                         'judgments_are_human_not_ai_generated': None},
        'cases': [{'id': f'V{i:03}', 'question': question, 'question_origin': 'assistant_prepared',
                   'human_review': blank_judgment()} for i, (_, question) in enumerate(prepared, 1)]}
    manifest = {'schema_version': 1, 'packet_id': packet['packet_id'],
                'packet_sha256': digest(packet), 'criteria': CRITERIA,
                'selector_sha256': hashlib.sha256((BASE/'regime_selector.py').read_bytes()).hexdigest(),
                'retriever_sha256': hashlib.sha256((BASE/'retrieve_bge.py').read_bytes()).hexdigest(),
                'corpus_sha256': hashlib.sha256((BASE/'data/chunks.json').read_bytes()).hexdigest(),
                'prepared_cases': [{'id': c['id'], 'question': c['question'], 'question_origin': c['question_origin'],
                                    'administrator_coverage_topic': prepared[i][0]} for i, c in enumerate(packet['cases'])],
                'private': 'Do not send this manifest, selector code, historical keys or rankings to the blinded reviewer.'}
    lines = ['# Independent human review worksheet', '', packet['purpose'], '',
             'The prompts were prepared by an assistant. All judgments below are blank. They must be supplied by an independent human; do not use an AI model to fill them.', '',
             'Use the complete corpus and any authoritative material needed to assess its limits. No retrieved excerpts or selected sources are supplied. Record missing facts and outside-corpus evidence rather than forcing a law selection.', '',
             'Complete the companion JSON as the machine-readable submission; this Markdown is a reading/capture aid. Keep the original prepared questions and IDs unchanged. Add at least ten new questions that you independently author, using H001, H002, etc. and question_origin="reviewer_authored".', '',
             '## Reviewer and independence attestation', '',
             '- Reviewer ID/name:', '- Relevant expertise:', '- Completion date (YYYY-MM-DD):',
             '- Independent of the selector development: yes/no',
             '- Have not seen selector predictions, historical answer keys or ranking results: yes/no',
             '- All submitted judgments are human-authored, not AI-generated: yes/no', '',
             '## Field instructions', '',
             '- review_status: reviewed or unresolved. An unresolved review cannot be imported as complete.',
             '- applicable_legislation: list the relevant document/law names; use [] only when justified.',
             '- supporting_articles: list objects with source_document, article, necessary (true/false), availability (in_corpus/outside_corpus/uncertain), and rationale. Use canonical document names and article labels when in the supplied corpus. Mark necessary only for evidence whose exclusion would materially impair the answer; distinguish optional/background provisions. Use [] with explanation if no article can be identified.',
             '- answerability: answerable / partially_answerable / unanswerable / out_of_scope / needs_clarification, assessed against the supplied corpus.',
             '- permitted_filter: general / domestic / no_filter. Choose no_filter when both regimes, uncertainty or outside-scope evidence make narrowing unsafe. This is your judgment, not a system prediction.',
             '- confidence: high / medium / low. Low confidence requires later adjudication.',
             '- explanation: explain applicability, assumptions, ambiguity and any need for clarification.',
             '- source_basis: cite the material consulted and relevant version/date; distinguish corpus text from current law.',
             '- coverage_tags: assign one or more of general_employment, domestic_workers, explicit_law, ambiguous_mixed, negated_contradictory, unanswerable_out_of_scope. These are your coverage annotations; no case-specific topic labels are supplied.', '',
             'A case may be fully reviewed yet legitimately require clarification. Do not invent an article or infer a legal regime merely to complete a field.', '']
    for case in packet['cases']:
        lines += [f"## {case['id']}", '', case['question'], '',
                  '- Applicable legislation:', '- Expected supporting articles (necessary/optional; corpus availability):',
                  '- Answerability / clarification needed:', '- Permitted filtering, if any:',
                  '- Confidence / explanation:', '- Source basis:', '- Coverage tags:', '- Review status:', '']
    write_new_json(paths[0], packet)
    paths[1].parent.mkdir(parents=True, exist_ok=True)
    with paths[1].open('x', encoding='utf-8') as file:
        file.write('\n'.join(lines))
    write_new_json(paths[2], manifest)
    return packet


def validate_submission(packet, manifest):
    check(isinstance(packet, dict) and isinstance(manifest, dict), 'Expected packet and manifest objects')
    check(packet.get('schema_version') == 1 and packet.get('packet_id') == manifest.get('packet_id'), 'Packet/version identity mismatch')
    reviewer = packet.get('reviewer', {})
    check(isinstance(reviewer, dict) and all(text(reviewer.get(k)) for k in ('reviewer_id', 'expertise', 'completed_at')),
          'Independent reviewer identity, expertise and completion date are required')
    from datetime import date
    check(re.fullmatch(r'\d{4}-\d{2}-\d{2}', reviewer['completed_at']) is not None,
          'Reviewer completion date must be YYYY-MM-DD')
    try:
        date.fromisoformat(reviewer['completed_at'])
    except (ValueError, TypeError):
        raise ValueError('Reviewer completion date must be YYYY-MM-DD') from None
    attestations = packet.get('attestations', {})
    check(isinstance(attestations, dict) and all(attestations.get(k) is True for k in (
        'independent_of_selector_development', 'not_seen_predictions_keys_or_rankings', 'judgments_are_human_not_ai_generated')),
        'All independent-human/blinding attestations must be explicitly true')
    cases = packet.get('cases')
    check(isinstance(cases, list) and bool(cases), 'Completed cases are required')
    check(all(isinstance(c, dict) and isinstance(c.get('id'), str) and re.fullmatch(r'[VH]\d{3}', c['id']) for c in cases), 'Case IDs must use Vnnn or Hnnn')
    check(len({c['id'] for c in cases}) == len(cases), 'Duplicate case IDs')
    prepared = {c['id']: c for c in manifest['prepared_cases']}
    check(set(prepared) <= {c['id'] for c in cases}, 'Prepared cases may not be silently removed')
    result = []
    for case in cases:
        check(set(case) == {'id', 'question', 'question_origin', 'human_review'}, 'Case fields must match the blinded worksheet')
        identifier = case['id']
        if identifier in prepared:
            check(case.get('question') == prepared[identifier]['question'] and case.get('question_origin') == 'assistant_prepared',
                  'Prepared questions or provenance were changed')
        else:
            check(identifier.startswith('H') and case.get('question_origin') == 'reviewer_authored' and text(case.get('question')),
                  'Additional cases must be independently reviewer-authored Hnnn questions')
        review = case.get('human_review')
        check(isinstance(review, dict) and set(review) == set(blank_judgment()), 'Human review fields must match the worksheet schema')
        check(review['review_status'] == 'reviewed', 'Every case requires a completed human review; unresolved is not complete')
        check(review['answerability'] in ('answerable', 'partially_answerable', 'unanswerable', 'out_of_scope', 'needs_clarification'), 'Invalid answerability judgment')
        check(review['permitted_filter'] in ('general', 'domestic', 'no_filter'), 'Invalid human filtering judgment')
        check(review['confidence'] in ('high', 'medium', 'low'), 'Invalid confidence')
        check(text(review['explanation']) and text(review['source_basis']), 'Human explanations and source basis are required')
        tags = review['coverage_tags']
        check(isinstance(tags, list) and bool(tags) and all(isinstance(t, str) and t in DOMAINS for t in tags) and len(set(tags)) == len(tags), 'Invalid or missing human coverage tags')
        laws = review['applicable_legislation']
        check(isinstance(laws, list) and all(text(x) for x in laws) and len(set(laws)) == len(laws), 'Applicable legislation must be a unique list')
        articles = review['supporting_articles']
        check(isinstance(articles, list), 'Supporting articles must be a list, possibly empty with explanation')
        identities = []
        for article in articles:
            check(isinstance(article, dict) and set(article) == {'source_document', 'article', 'necessary', 'availability', 'rationale'}, 'Invalid supporting-article schema')
            check(all(text(article[k]) for k in ('source_document', 'article', 'rationale')), 'Supporting article identity and rationale required')
            check(article['source_document'] in laws, 'Supporting source must be included in applicable legislation')
            check(type(article['necessary']) is bool and article['availability'] in ('in_corpus', 'outside_corpus', 'uncertain'), 'Invalid necessity or corpus-availability judgment')
            identities.append((article['source_document'], article['article']))
        check(len(set(identities)) == len(identities), 'Duplicate supporting articles')
        if review['answerability'] in ('answerable', 'partially_answerable'):
            check(any(a['availability'] == 'in_corpus' for a in articles), 'Answerable cases require at least one in-corpus supporting article')
        if review['answerability'] in ('out_of_scope', 'needs_clarification'):
            check(review['permitted_filter'] == 'no_filter', 'Outside-scope/clarification cases must not force a corpus law filter')
        result.append(copy.deepcopy(case))
    return result


def import_review(packet_path, manifest_path, output):
    output = require_new_output(output)
    check(disjoint(output), 'Output overlaps protected index')
    packet, manifest = load_json(packet_path), load_json(manifest_path)
    cases = validate_submission(packet, manifest)
    validate_frozen_inputs(manifest)
    imported = {'schema_version': 1, 'status': 'human_reviewed_import',
                'judgment_provenance': 'Human independence is attested by the submitter, not independently authenticated by software.',
                'packet_id': packet['packet_id'], 'reviewer': packet['reviewer'], 'attestations': packet['attestations'],
                'cases': cases, 'manifest': manifest,
                'submission_sha256': hashlib.sha256(Path(packet_path).read_bytes()).hexdigest(),
                'manifest_sha256': hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()}
    write_new_json(output, imported)
    return imported


def validate_frozen_inputs(manifest):
    for field, relative in (('selector_sha256', 'regime_selector.py'), ('retriever_sha256', 'retrieve_bge.py'),
                            ('corpus_sha256', 'data/chunks.json')):
        check(manifest.get(field) == hashlib.sha256((BASE/relative).read_bytes()).hexdigest(),
              'Frozen selector, retriever or corpus changed; start a new validation round')
    check(manifest.get('criteria') == CRITERIA, 'Promotion criteria differ from the preregistered version')


def validate_import(imported):
    check(isinstance(imported, dict) and imported.get('status') == 'human_reviewed_import', 'Only a complete human-reviewed import may be evaluated')
    validate_submission(imported, imported['manifest'])
    validate_frozen_inputs(imported['manifest'])
    return imported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--packet', type=Path, required=True)
    prepare.add_argument('--markdown', type=Path, required=True)
    prepare.add_argument('--manifest', type=Path, required=True)
    ingest = sub.add_parser('import')
    ingest.add_argument('--input', type=Path, required=True)
    ingest.add_argument('--manifest', type=Path, required=True)
    ingest.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            packet = prepare_packet(args.packet, args.markdown, args.manifest)
            print(f"Prepared {len(packet['cases'])} blinded prompts; no human judgments supplied.")
        else:
            result = import_review(args.input, args.manifest, args.output)
            print(f"Imported {len(result['cases'])} reviewer-attested cases; not yet evaluated or approved for production.")
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
