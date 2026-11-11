"""Evaluate only completed reviewer-attested imports, in isolated Chroma copies.

No paid APIs, reranking, hybrid retrieval, generation or production promotion.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

from artifact_io import require_new_output, write_new_json
from independent_review import load_json, validate_import, CRITERIA, DOMAINS
from index_integrity import digest, index_fingerprint, logical_differences
from index_isolation import locked_snapshot, tree_hashes, install_chroma_guard
from index_paths import PROTECTED_INDEX, disjoint, resolve_index_path
from regime_selector import select_regime

KS = (1, 3, 5, 10)


def retrieve_pair(question, sources, collection, vector, ordinal=0):
    """Runtime input excludes every human judgment and expected article."""
    from phase42_eval import dense_query
    start = time.perf_counter()
    selection = select_regime(question, sources)
    selection_ms = (time.perf_counter()-start)*1000
    if selection['where'] is None:
        start = time.perf_counter(); baseline = dense_query(collection, vector)
        elapsed = (time.perf_counter()-start)*1000
        return {'baseline': baseline, 'experimental': baseline, 'selection': selection,
                'baseline_ms': elapsed, 'experimental_ms': elapsed, 'selection_ms': selection_ms}
    measured = {}
    arms = ('baseline', 'experimental') if ordinal % 2 == 0 else ('experimental', 'baseline')
    for arm in arms:
        start = time.perf_counter()
        chunks = dense_query(collection, vector, selection['where'] if arm == 'experimental' else None)
        measured[arm] = chunks
        measured[arm + '_ms'] = (time.perf_counter()-start)*1000
    return dict(measured, selection=selection, selection_ms=selection_ms)


def pairs(chunks):
    return {(c['source_document'], c['article']) for c in chunks}


def score(case, retrieved, encode_ms):
    from eval_answers import retrieval_metrics
    review = case['human_review']
    expected = [a for a in review['supporting_articles'] if a['availability'] == 'in_corpus']
    needed = [a for a in review['supporting_articles'] if a['necessary']]
    selection = retrieved['selection']
    allowed = selection['sources'] if selection['where'] else None
    actual_policy = selection['regime'] if allowed is not None else 'no_filter'
    excluded = [a for a in needed if allowed is not None and a['source_document'] not in allowed]
    needed_in_corpus = pairs([a for a in needed if a['availability'] == 'in_corpus'])
    observed_loss = needed_in_corpus & (pairs(retrieved['baseline']) - pairs(retrieved['experimental']))
    row = {'id': case['id'], 'question_origin': case['question_origin'],
           'review_confidence': review['confidence'], 'coverage_tags': review['coverage_tags'],
           'human_judgment': review, 'automatic_selection': selection,
           'selection_matches_human': actual_policy == review['permitted_filter'],
           'incorrect_forced_filter': allowed is not None and actual_policy != review['permitted_filter'],
           'conservative_no_filter': allowed is None and review['permitted_filter'] != 'no_filter',
           'necessary_source_exclusions': excluded,
           'observed_necessary_evidence_losses': [list(a) for a in sorted(observed_loss)],
           'encode_ms': encode_ms, 'selection_ms': retrieved['selection_ms'], 'arms': {}}
    for arm in ('baseline', 'experimental'):
        row['arms'][arm] = {
            'metrics': {str(k): retrieval_metrics(retrieved[arm], expected, k) for k in KS} if expected else {},
            'query_ms': retrieved[arm + '_ms'],
            'total_ms': encode_ms + retrieved[arm + '_ms'] + (retrieved['selection_ms'] if arm == 'experimental' else 0),
            'captured_evidence': retrieved[arm],
            'evidence_sha256': digest(retrieved[arm]),
        }
    return row


def percentile95(values):
    return sorted(values)[max(0, math.ceil(.95*len(values))-1)] if values else None


def assessment(rows, criteria=None):
    criteria = criteria or CRITERIA
    scored = [r for r in rows if r['arms']['baseline']['metrics']]
    coverage = Counter(tag for r in rows for tag in r['coverage_tags'])
    excluded = [r['id'] for r in rows if r['necessary_source_exclusions'] or r['observed_necessary_evidence_losses']]
    incorrect = [r['id'] for r in rows if r['incorrect_forced_filter']]
    regressions = {str(k): {metric: [r['id'] for r in scored if
        r['arms']['experimental']['metrics'][str(k)][metric] < r['arms']['baseline']['metrics'][str(k)][metric]]
        for metric in ('hit', 'recall', 'rr')} for k in KS}
    aggregates = {arm: {str(k): {metric: statistics.mean(r['arms'][arm]['metrics'][str(k)][metric] for r in scored)
                               if scored else None for metric in ('hit', 'recall', 'rr', 'precision')}
                        for k in KS} for arm in ('baseline', 'experimental')}
    latency = {}
    for arm in ('baseline', 'experimental'):
        values = [r['arms'][arm]['total_ms'] for r in rows]
        latency[arm] = {'median_ms': statistics.median(values) if values else None, 'p95_ms': percentile95(values)}
    uncertain = [r['id'] for r in rows if r['review_confidence'] == 'low' or
                 any(a['availability'] == 'uncertain' for a in r['human_judgment']['supporting_articles'])]
    gates = {
        'minimum_case_count': len(rows) >= criteria['minimum_total_cases'],
        'reviewer_authored_case_count': sum(r['question_origin'] == 'reviewer_authored' for r in rows) >= criteria['minimum_reviewer_authored_cases'],
        'coverage': all(coverage[d] >= criteria['minimum_cases_per_domain'] for d in DOMAINS),
        'minimum_scored_cases': len(scored) >= criteria['minimum_article_scored_cases'],
        'necessary_evidence_coverage': sum(any(a['necessary'] and a['availability'] == 'in_corpus'
            for a in r['human_judgment']['supporting_articles']) for r in rows) >= criteria['minimum_necessary_evidence_cases'],
        'actual_filter_coverage': sum(r['automatic_selection']['where'] is not None for r in rows) >= criteria['minimum_filtered_cases'],
        'human_filter_policy_balance': all(sum(r['human_judgment']['permitted_filter'] == regime for r in rows)
            >= criteria['minimum_filter_policy_cases_per_regime'] for regime in ('general', 'domestic')),
        'human_no_filter_coverage': sum(r['human_judgment']['permitted_filter'] == 'no_filter' for r in rows) >= criteria['minimum_no_filter_cases'],
        'no_harmful_necessary_evidence_exclusion': len(excluded) <= criteria['maximum_harmful_exclusion_cases'],
        'no_incorrect_forced_filters': len(incorrect) <= criteria['maximum_incorrect_forced_filters'],
        'no_per_case_ranking_regressions': not any(ids for by_metric in regressions.values() for ids in by_metric.values()),
        'no_low_confidence_or_uncertain_availability': not uncertain,
        'aggregate_hit_and_recall_noninferior': bool(scored) and all(
            aggregates['experimental']['10'][metric] >= aggregates['baseline']['10'][metric] for metric in ('hit', 'recall')),
        'median_latency': bool(rows) and latency['experimental']['median_ms'] <= latency['baseline']['median_ms']*criteria['median_latency_ratio_limit'] + criteria['latency_allowance_ms'],
        'p95_latency': bool(rows) and latency['experimental']['p95_ms'] <= latency['baseline']['p95_ms']*criteria['p95_latency_ratio_limit'] + criteria['latency_allowance_ms'],
    }
    return {'status': 'awaiting_manual_signoff' if all(gates.values()) else 'not_ready',
            'production_promoted': False, 'production_approved': False,
            'independent_review_status': 'reviewer_attested_import_received' if rows else 'not_supplied',
            'questions': len(rows), 'article_metric_denominator': len(scored),
            'human_routing_denominator': len(rows), 'routing_matches': sum(r['selection_matches_human'] for r in rows),
            'conservative_no_filter_count': sum(r['conservative_no_filter'] for r in rows),
            'incorrect_forced_filter_cases': incorrect, 'harmful_exclusion_cases': excluded,
            'low_confidence_or_uncertain_cases': uncertain,
            'coverage': dict(coverage), 'metrics': aggregates, 'regressions': regressions, 'latency': latency,
            'automated_gates': gates, 'criteria': criteria,
            'outstanding_manual_requirements': ['Authenticate reviewer independence and expertise.',
                'Resolve Q041 and Q068 in a separate key review after the blinded submission is locked.',
                'Inspect actual passages for claim support; article presence is only a proxy.',
                'Obtain explicit production approval; this tool never changes production.']}


def worker(root):
    root = Path(root).resolve()
    manifest = load_json(root/'source-baseline.json')
    imported = validate_import(load_json(root/'human-import.json'))
    target = root/'working'
    if not disjoint(root) or not disjoint(root, manifest['source']) or tree_hashes(target) != manifest['hashes']:
        raise ValueError('Worker requires a verified isolated copy')
    os.environ.update(RAG_TEST_INDEX_ROOT=str(root), RAG_INDEX_PATH=str(target), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
    if resolve_index_path() != target:
        raise ValueError('Index path mismatch')
    opened = install_chroma_guard(target)
    import retrieve_bge as retriever
    collection = retriever.get_collection()
    before = index_fingerprint(retriever.client)
    stored = collection.get(include=['metadatas', 'documents'])
    metadata = stored['metadatas']
    from independent_review import BASE
    exported = load_json(BASE/'data/chunks.json')
    corpus_match = sorted((m['source_document'], m.get('article'), t) for m, t in zip(metadata, stored['documents'])) == sorted(
        (c['source_document'], c['article'], c['text']) for c in exported)
    sources = sorted({m['source_document'] for m in metadata})
    available = {(m['source_document'], m.get('article')) for m in metadata}
    missing = [case['id'] for case in imported['cases'] if any(
        a['availability'] == 'in_corpus' and (a['source_document'], a['article']) not in available
        for a in case['human_review']['supporting_articles'])]
    rows = []
    result = {'api_requests': 0, 'human_import_sha256': digest(imported), 'status': 'corpus_review_required' if missing or not corpus_match else 'evaluated',
              'missing_in_corpus_reference_cases': missing, 'selector_sha256': imported['manifest']['selector_sha256'],
              'index_logical_sha256': digest(before), 'reviewed_dataset': imported,
              'stored_index_matches_reviewed_export': corpus_match,
              'evaluation_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        if not missing and corpus_match:
            start = time.perf_counter(); model = retriever.get_model()
            result['model_load_seconds'] = time.perf_counter()-start
            for ordinal, case in enumerate(imported['cases']):
                start = time.perf_counter()
                vector = model.encode(retriever.QUERY_PREFIX+case['question'], normalize_embeddings=True).tolist()
                encoded_ms = (time.perf_counter()-start)*1000
                retrieved = retrieve_pair(case['question'], sources, collection, vector, ordinal)
                row = score(case, retrieved, encoded_ms)
                rows.append(row)
                write_new_json(root/'cases'/(case['id']+'.json'), row)
            result['assessment'] = assessment(rows, imported['manifest']['criteria'])
        result['rows'] = rows
        after = index_fingerprint(retriever.client)
    finally:
        retriever.client.close(); retriever.client = None; retriever.client_path = None
    retriever.get_collection()
    try:
        reopened = index_fingerprint(retriever.client)
    finally:
        retriever.client.close()
    result['isolation'] = {'opened_paths': sorted(set(opened)), 'snapshot_byte_match': True,
                           'logical_differences': logical_differences(before, after),
                           'reopen_differences': logical_differences(before, reopened)}
    write_new_json(root/'worker-results.json', result)


def run(import_path, output):
    output = require_new_output(output)
    if not disjoint(output) or not disjoint(Path(tempfile.gettempdir())):
        raise ValueError('Output or temporary storage overlaps protected index')
    # Validate complete human data and frozen selector BEFORE touching any index.
    imported = validate_import(load_json(import_path))
    root = Path(tempfile.mkdtemp(prefix='compliance-rag-independent-'))
    write_new_json(root/'human-import.json', imported)
    result = {'status': 'blocked', 'workspace': str(root), 'api_requests': 0, 'production_promoted': False}
    with locked_snapshot(PROTECTED_INDEX) as snapshot:
        baseline = snapshot.hashes()
        write_new_json(root/'source-baseline.json', {'source': str(PROTECTED_INDEX), 'hashes': baseline})
        snapshot.copy_to(root/'working')
        try:
            process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root)],
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
            if process.returncode:
                result['worker_exit'] = process.returncode
            else:
                result.update(load_json(root/'worker-results.json'))
                if result['isolation']['logical_differences'] or result['isolation']['reopen_differences']:
                    result['status'] = 'integrity_failure'
        finally:
            result['original_hashes_unchanged'] = snapshot.hashes() == baseline
        if not result['original_hashes_unchanged']:
            result['status'] = 'integrity_failure'
    write_new_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            worker(args.worker)
        except Exception as exc:
            write_new_json(args.worker/'failure.json', {'type': type(exc).__name__, 'code': getattr(exc, 'code', 'validation_failed')})
            raise SystemExit(2)
    else:
        if not args.input or not args.output:
            parser.error('--input and --output are required')
        try:
            result = run(args.input, args.output)
        except (ValueError, FileExistsError) as exc:
            parser.error(str(exc))
        print(json.dumps({'status': result['status'], 'api_requests': 0, 'production_promoted': False}))
        if result['status'] != 'evaluated':
            raise SystemExit(2)


if __name__ == '__main__':
    main()
