"""Offline baseline/Phase-4.1/Phase-4.2 filtering comparison; no reranking or APIs."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

from artifact_io import require_new_output, write_new_json
from index_integrity import digest, index_fingerprint, logical_differences
from index_isolation import locked_snapshot, tree_hashes, install_chroma_guard
from index_paths import PROTECTED_INDEX, disjoint, resolve_index_path
from regime_selector import select_regime, CATALOG, VERSION

BASE = Path(__file__).resolve().parent
CHALLENGE = BASE / 'tests/fixtures/phase42_challenge.json'
ARMS = ('baseline', 'phase41', 'phase42')
KS = (1, 3, 5, 10)


def selections(question, source_documents):
    # Audit comparator only: no lexical reranker or candidate fusion is invoked.
    from retrieval_experiments import route, allowed_sources
    old = route(question)
    old_sources = [s for s in (allowed_sources(old) or []) if s in source_documents]
    return {'baseline': {'status': 'unfiltered', 'regime': None, 'where': None},
            'phase41': {'status': 'filtered' if old_sources else 'unfiltered', 'regime': old if old_sources else None,
                        'where': {'source_document': {'$in': sorted(old_sources)}} if old_sources else None},
            'phase42': select_regime(question, source_documents)}


def dense_query(collection, vector, where=None):
    count = collection.count()
    if type(count) is not int or count < 1:
        raise ValueError('Collection contains no passages')
    kwargs = {} if where is None else {'where': where}
    result = collection.query(query_embeddings=[vector], n_results=min(10, count),
                              include=['documents', 'metadatas', 'distances'], **kwargs)
    return [dict(m, chunk_id=i, text=t, distance=float(d)) for i, t, m, d in
            zip(result['ids'][0], result['documents'][0], result['metadatas'][0], result['distances'][0])]


def retrieve_variants(question, source_documents, collection, vector, ordinal=0):
    """Runtime boundary accepts no answer key, evaluation ID, or expected articles."""
    start = time.perf_counter()
    plans = selections(question, source_documents)
    selection_ms = (time.perf_counter() - start)*1000
    # Equal filters share a query within this comparison, avoiding needless work.
    # This is experiment-only reuse, not a production result cache.
    unique = {digest(plan['where']): plan['where'] for plan in plans.values()}
    keys = list(unique)
    offset = ordinal % len(keys)
    measured = {}
    for key in keys[offset:] + keys[:offset]:
        start = time.perf_counter()
        chunks = dense_query(collection, vector, unique[key])
        measured[key] = (chunks, (time.perf_counter()-start)*1000)
    return {name: {'selection': plan, 'chunks': measured[digest(plan['where'])][0],
                   'query_ms': measured[digest(plan['where'])][1], 'selection_bundle_ms': selection_ms}
            for name, plan in plans.items()}


def score_case(case, variants, encode_ms):
    """Answer keys enter here, strictly after all routing/retrieval is complete."""
    from eval_answers import retrieval_metrics
    row = {'id': case['id'], 'category': case['category'], 'encode_ms': encode_ms, 'arms': {}}
    for name, result in variants.items():
        chunks, selection = result['chunks'], result['selection']
        where = selection['where']
        allowed = where['source_document']['$in'] if where else None
        row['arms'][name] = {
            'selection': selection, 'query_ms': result['query_ms'],
            'selection_bundle_ms': result['selection_bundle_ms'],
            'metrics': {str(k): retrieval_metrics(chunks, case['expected_articles'], k) for k in KS}
                       if case['expected_articles'] else {},
            'candidates': [{key: c.get(key) for key in ('chunk_id', 'source_document', 'article', 'distance')}
                           | {'text_sha256': digest(c['text'])} for c in chunks],
            'expected_sources_excluded': [a for a in case['expected_articles'] if allowed is not None and a['source_document'] not in allowed],
        }
        if 'expected_policy' in case:
            policy = selection['regime'] if where else 'no_filter'
            row['arms'][name]['policy_match'] = policy == case['expected_policy']
            row['arms'][name]['unsafe_filter'] = bool(where and policy != case['expected_policy'])
    if 'expected_policy' in case:
        row['expected_policy'] = case['expected_policy']
    return row


def summarize(rows):
    result = {'questions': len(rows), 'scored_questions': sum(bool(r['arms']['baseline']['metrics']) for r in rows), 'arms': {}}
    for name in ARMS:
        scored = [r for r in rows if r['arms'][name]['metrics']]
        policies = [r for r in rows if 'expected_policy' in r]
        metrics = {str(k): {m: statistics.mean(r['arms'][name]['metrics'][str(k)][m] for r in scored)
                           if scored else None for m in ('hit', 'rr', 'recall', 'precision')} for k in KS}
        regressions = {str(k): {m: [r['id'] for r in scored if r['arms'][name]['metrics'][str(k)][m] < r['arms']['baseline']['metrics'][str(k)][m]]
                              for m in ('hit', 'rr', 'recall')} for k in KS}
        values = [r['arms'][name]['query_ms'] for r in rows]
        result['arms'][name] = {
            'metrics': metrics, 'regressions': regressions,
            'hit10_improvements': [r['id'] for r in scored if r['arms'][name]['metrics']['10']['hit'] > r['arms']['baseline']['metrics']['10']['hit']],
            'changed_rankings': [r['id'] for r in rows if [c['chunk_id'] for c in r['arms'][name]['candidates']] != [c['chunk_id'] for c in r['arms']['baseline']['candidates']]],
            'expected_source_exclusions': [r['id'] for r in rows if r['arms'][name]['expected_sources_excluded']],
            'selection_counts': dict(Counter(r['arms'][name]['selection']['status'] for r in rows)),
            'policy_matches': sum(r['arms'][name]['policy_match'] for r in policies), 'policy_denominator': len(policies),
            'unsafe_filter_ids': [r['id'] for r in policies if r['arms'][name]['unsafe_filter']],
            'policy_mismatch_ids': [r['id'] for r in policies if not r['arms'][name]['policy_match']],
            'median_query_ms': statistics.median(values),
            'median_encode_plus_query_ms': statistics.median(r['encode_ms'] + r['arms'][name]['query_ms'] for r in rows),
            'median_selection_bundle_ms': statistics.median(r['arms'][name]['selection_bundle_ms'] for r in rows),
        }
    return result


def worker(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'source-baseline.json').read_text(encoding='utf-8'))
    target = root / 'working'
    if not disjoint(root) or not disjoint(root, manifest['source']) or tree_hashes(target) != manifest['hashes']:
        raise RuntimeError('Unverified snapshot')
    os.environ.update(RAG_TEST_INDEX_ROOT=str(root), RAG_INDEX_PATH=str(target), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
    if resolve_index_path() != target:
        raise RuntimeError('Unsafe index path')
    opened = install_chroma_guard(target)
    import retrieve_bge as retriever
    from eval_answers import load_eval_set
    from phase4_eval import fingerprint_files
    collection = retriever.get_collection()
    before = index_fingerprint(retriever.client)
    metadata = collection.get(include=['metadatas'])['metadatas']
    source_documents = sorted({m['source_document'] for m in metadata})
    dataset = load_eval_set()
    challenge = json.loads(CHALLENGE.read_text(encoding='utf-8'))
    # Verify provisional article references exist; this is not legal validation.
    available = {(m['source_document'], m.get('article')) for m in metadata}
    if any((a['source_document'], a['article']) not in available for q in challenge['questions'] for a in q['expected_articles']):
        raise ValueError('Challenge article is not present in stored metadata')
    fingerprints = fingerprint_files()
    fingerprints.update(selector_sha256=hashlib.sha256((BASE/'regime_selector.py').read_bytes()).hexdigest(),
                        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        challenge_sha256=hashlib.sha256(CHALLENGE.read_bytes()).hexdigest(),
                        catalog_sha256=digest(CATALOG), index_logical_sha256=digest(before),
                        source_files_sha256=digest(manifest['hashes']))
    start = time.perf_counter(); model = retriever.get_model()
    load_seconds = time.perf_counter() - start
    results = {}
    try:
        for suite, cases in (('existing74', dataset), ('challenge40', challenge['questions'])):
            rows = []
            for ordinal, case in enumerate(cases):
                start = time.perf_counter()
                vector = model.encode(retriever.QUERY_PREFIX + case['question'], normalize_embeddings=True).tolist()
                encode_ms = (time.perf_counter()-start)*1000
                variants = retrieve_variants(case['question'], source_documents, collection, vector, ordinal)
                row = score_case(case, variants, encode_ms)
                rows.append(row)
                write_new_json(root / suite / (case['id'] + '.json'), row)
            results[suite] = {'rows': rows, 'summary': summarize(rows)}
        after = index_fingerprint(retriever.client)
    finally:
        retriever.client.close(); retriever.client = None; retriever.client_path = None
    retriever.get_collection()
    try:
        reopened = index_fingerprint(retriever.client)
    finally:
        retriever.client.close()
    write_new_json(root / 'worker-results.json', {
        'api_requests': 0, 'reranking': False, 'hybrid_retrieval': False, 'selector_version': VERSION,
        'fingerprints': fingerprints, 'catalog': CATALOG, 'available_sources': source_documents,
        'model_load_seconds': load_seconds, 'challenge_provenance': challenge['provenance'],
        'suites': results,
        'isolation': {'opened_paths': sorted(set(opened)), 'snapshot_byte_match': True,
                      'logical_differences': logical_differences(before, after),
                      'reopen_differences': logical_differences(before, reopened)}})


def run(output):
    output = require_new_output(output)
    if not disjoint(output) or not disjoint(Path(tempfile.gettempdir())):
        raise ValueError('Experiment output/storage overlaps protected index')
    root = Path(tempfile.mkdtemp(prefix='compliance-rag-regimes-'))
    print(f'Offline isolated workspace: {root}', flush=True)
    result = {'status': 'blocked', 'workspace': str(root), 'api_requests': 0}
    with locked_snapshot(PROTECTED_INDEX) as snapshot:
        baseline = snapshot.hashes()
        write_new_json(root / 'source-baseline.json', {'source': str(PROTECTED_INDEX), 'hashes': baseline})
        snapshot.copy_to(root / 'working')
        try:
            process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root)],
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
            if process.returncode:
                result['worker_exit'] = process.returncode
            else:
                result.update(json.loads((root / 'worker-results.json').read_text(encoding='utf-8')))
                result['status'] = 'completed' if not result['isolation']['logical_differences'] and not result['isolation']['reopen_differences'] else 'integrity_failure'
        finally:
            result['original_hashes_unchanged'] = snapshot.hashes() == baseline
        if not result['original_hashes_unchanged']:
            result['status'] = 'integrity_failure'
    write_new_json(output, result)
    print(f"Status: {result['status']}; original unchanged: {result['original_hashes_unchanged']}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            worker(args.worker)
        except Exception as exc:
            write_new_json(args.worker / 'failure.json', {'type': type(exc).__name__, 'code': getattr(exc, 'code', 'experiment_failed')})
            raise SystemExit(2)
    else:
        if not args.output:
            parser.error('--output is required')
        try:
            result = run(args.output)
        except (ValueError, RuntimeError, FileExistsError) as exc:
            parser.error(str(exc))
        if result['status'] != 'completed':
            raise SystemExit(2)


if __name__ == '__main__':
    main()
