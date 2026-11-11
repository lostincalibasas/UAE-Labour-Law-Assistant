"""Offline-only retrieval experiments. Never imported by the production retriever."""
import argparse
import copy
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time

from artifact_io import require_new_output, write_new_json
from index_integrity import digest, index_fingerprint, logical_differences
from index_isolation import locked_snapshot, tree_hashes, install_chroma_guard
from index_paths import PROTECTED_INDEX, disjoint, resolve_index_path

GENERAL = 'Federal Decree-Law No. 33 of 2021'
DOMESTIC = ('Federal Decree-Law No. 9 of 2022', 'Cabinet Decision No. 106 of 2022',
            'Cabinet Resolution No. 92 of 2022')
MISS_IDS = {'Q027', 'Q041', 'Q068', 'Q072'}
STOP = set('a an the is are was were be been to of for and or in on at by with from as it its my me i we you your can does do how what when which who under per much many'.split())
CONFIG = {'candidate_depths': [10, 20, 50], 'served_k': 10, 'metric_ks': [1, 3, 5, 10, 20, 50],
          'rrf_constant': 60, 'bm25_k1': 1.2, 'bm25_b': 0.75,
          'routing': 'Explicit general/private-sector scope first; explicit domestic/household next; otherwise no filter.',
          'api_requests': 0, 'parameter_selection': 'Fixed before evaluation; no label-dependent retrieval rules.'}


def route(question):
    """Use question wording alone; never expected articles, facts, categories or IDs."""
    text = question.casefold()
    if re.search(r'\b(private[ -]sector|(?:main|general) (?:uae )?labou?r law)\b', text):
        return 'general'
    if re.search(r'\b(domestic|household)\b', text):
        return 'domestic'
    return 'unspecified'


def allowed_sources(regime):
    return (GENERAL,) if regime == 'general' else DOMESTIC if regime == 'domestic' else None


def filter_candidates(chunks, regime):
    allowed = allowed_sources(regime)
    return [c for c in chunks if allowed is None or c['source_document'] in allowed]


def terms(text):
    # Conservative tokenization, no hand-written aliases for evaluation questions.
    return [t for t in re.findall(r'[a-z0-9]+', text.casefold()) if t not in STOP]


class LexicalReranker:
    """BM25 computed from stored texts; weighted only by fixed RRF ranks."""
    def __init__(self, chunks):
        self.counts = {c['chunk_id']: Counter(terms(c['text'])) for c in chunks}
        self.lengths = {k: sum(v.values()) for k, v in self.counts.items()}
        self.average = sum(self.lengths.values()) / max(len(chunks), 1)
        df = Counter(t for counts in self.counts.values() for t in counts)
        self.idf = {t: math.log(1 + (len(chunks) - n + .5) / (n + .5)) for t, n in df.items()}

    def score(self, question, chunk):
        counts = self.counts[chunk['chunk_id']]
        length = self.lengths[chunk['chunk_id']]
        k1, b = CONFIG['bm25_k1'], CONFIG['bm25_b']
        return sum(self.idf.get(t, 0) * counts[t] * (k1 + 1) /
                   (counts[t] + k1 * (1 - b + b * length / max(self.average, 1)))
                   for t in set(terms(question)) if counts[t])

    def rerank(self, question, candidates):
        if not candidates:
            return []
        scores = [self.score(question, c) for c in candidates]
        if not any(scores):
            return list(candidates)
        lexical_order = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
        lexical_ranks = {i: rank for rank, i in enumerate(lexical_order, 1)}
        c = CONFIG['rrf_constant']
        order = sorted(range(len(candidates)),
                       key=lambda i: (-(1 / (c + i + 1) + 1 / (c + lexical_ranks[i])), i))
        return [candidates[i] for i in order]


def query(collection, vector, k, regime='unspecified'):
    count = collection.count()
    if type(count) is not int or count <= 0:
        raise ValueError('Collection must contain stored passages')
    kwargs = {}
    allowed = allowed_sources(regime)
    if allowed:
        kwargs['where'] = {'source_document': {'$in': list(allowed)}}
    # Same normalized BGE query and cosine collection; only candidate depth/filter varies.
    result = collection.query(query_embeddings=[vector], n_results=min(k, count),
                              include=['documents', 'metadatas', 'distances'], **kwargs)
    return [dict(m, chunk_id=i, text=t, distance=float(d)) for i, t, m, d in
            zip(result['ids'][0], result['documents'][0], result['metadatas'][0], result['distances'][0])]


def metrics(chunks, expected):
    from eval_answers import retrieval_metrics
    return {str(k): retrieval_metrics(chunks, expected, k) for k in CONFIG['metric_ks']} if expected else {}


def compare(rows):
    names = list(rows[0]['variants']) if rows else []
    report = {}
    for name in names:
        scored = [r for r in rows if r['variants'][name]['metrics']]
        improved, regressed, recall_regressed = [], [], []
        for r in scored:
            a, b = r['variants']['baseline10']['metrics']['10'], r['variants'][name]['metrics']['10']
            if b['hit'] > a['hit']: improved.append(r['id'])
            if b['hit'] < a['hit']: regressed.append(r['id'])
            if b['recall'] < a['recall']: recall_regressed.append(r['id'])
        report[name] = {'denominator': len(scored), 'metrics': {
            str(k): {m: statistics.mean(r['variants'][name]['metrics'][str(k)][m] for r in scored)
                     for m in ('hit', 'rr', 'recall', 'precision')} for k in CONFIG['metric_ks']},
            'hit_improvements_at_10': improved, 'hit_regressions_at_10': regressed,
            'recall_regressions_at_10': recall_regressed,
            'regressions_by_k': {str(k): {
                m: [r['id'] for r in scored if r['variants'][name]['metrics'][str(k)][m]
                    < r['variants']['baseline10']['metrics'][str(k)][m]]
                for m in ('hit', 'recall', 'rr')} for k in (1, 3, 5, 10)},
            'median_query_plus_rerank_ms': statistics.median(r['variants'][name]['retrieval_ms'] for r in rows),
            'median_total_ms_excluding_model_load': statistics.median(r['encode_ms'] + r['variants'][name]['retrieval_ms'] for r in rows),
            'other_questions': {str(k): {
                'denominator': sum(r['id'] not in MISS_IDS for r in scored),
                'hit': statistics.mean(r['variants'][name]['metrics'][str(k)]['hit'] for r in scored if r['id'] not in MISS_IDS),
                'recall': statistics.mean(r['variants'][name]['metrics'][str(k)]['recall'] for r in scored if r['id'] not in MISS_IDS)
            } for k in (1, 3, 5, 10)}}
    return report


def replay_scoped(input_path, output):
    """Adaptive follow-up: route-gated experiment, replayed without any DB/model."""
    output = require_new_output(output)
    if not disjoint(output):
        raise ValueError('Output overlaps protected index')
    raw = Path(input_path).read_bytes()
    source = json.loads(raw)
    if source.get('status') != 'completed' or not source.get('original_hashes_unchanged'):
        raise ValueError('Replay requires a successful isolated experiment')
    if source['isolation']['logical_differences'] or source['isolation']['reopen_differences']:
        raise ValueError('Replay source failed logical integrity')
    rows = copy.deepcopy(source['rows'])
    for row in rows:
        chosen = 'baseline10' if row['regime'] == 'unspecified' else 'prefilter_rrf50_top10'
        row['variants']['scoped_prefilter_rrf50_top10'] = copy.deepcopy(row['variants'][chosen])
    result = {'status': 'completed', 'api_requests': 0, 'index_opened': False,
              'source_sha256': hashlib.sha256(raw).hexdigest(), 'source': str(input_path),
              'design': 'Adaptive follow-up after observing Q004 regression: apply filtering/reranking only with explicit regime, otherwise retain baseline10. No question IDs or answer labels used by the gate.',
              'latency_note': 'Branch timings reused from source experiment; not an independent end-to-end timing trial.',
              'limitations': 'Development-set exploration, not a held-out validation or a production recommendation.',
              'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'rows': rows, 'summary': compare(rows)}
    write_new_json(output, result)
    return result


def exact_ranks(vector, stored, embeddings):
    vnorm = math.sqrt(sum(v*v for v in vector))
    scores = []
    for c, emb in zip(stored, embeddings):
        enorm = math.sqrt(sum(float(x)**2 for x in emb))
        distance = 1 - sum(float(x)*y for x, y in zip(emb, vector)) / (enorm * vnorm)
        scores.append((distance, str(c['chunk_id']), c))
    return [dict(c, distance=d) for d, _, c in sorted(scores, key=lambda x: (x[0], x[1]))]


def worker(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'source-baseline.json').read_text(encoding='utf-8'))
    target = root / 'working'
    if not disjoint(root) or not disjoint(root, manifest['source']) or tree_hashes(target) != manifest['hashes']:
        raise RuntimeError('Unverified snapshot')
    os.environ.update(RAG_TEST_INDEX_ROOT=str(root), RAG_INDEX_PATH=str(target), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
    if resolve_index_path() != target:
        raise RuntimeError('Index path mismatch')
    opened = install_chroma_guard(target)
    import retrieve_bge as retriever
    from eval_answers import load_eval_set, key
    from phase4_eval import fingerprint_files, diagnose
    collection = retriever.get_collection()
    before = index_fingerprint(retriever.client)
    batch = collection.get(include=['documents', 'metadatas', 'embeddings'])
    stored = [dict(m, chunk_id=i, text=t) for i, t, m in zip(batch['ids'], batch['documents'], batch['metadatas'])]
    reranker = LexicalReranker(stored)
    start = time.perf_counter()
    model = retriever.get_model()
    model_load_seconds = time.perf_counter() - start
    rows = []
    fingerprints = fingerprint_files()
    fingerprints['experiment_code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fingerprints['index_logical_sha256'] = digest(before)
    fingerprints['source_files_sha256'] = digest(manifest['hashes'])
    try:
        for ordinal, q in enumerate(load_eval_set()):
            question = q['question']
            regime = route(question)
            started = time.perf_counter()
            vector = model.encode(retriever.QUERY_PREFIX + question, normalize_embeddings=True).tolist()
            row = {'id': q['id'], 'regime': regime, 'encode_ms': (time.perf_counter()-started)*1000, 'variants': {}}
            pools, times = {}, {}
            # Rotate query order across questions to reduce a fixed warm-cache advantage.
            depths = CONFIG['candidate_depths']
            for k in depths[ordinal % 3:] + depths[:ordinal % 3]:
                started = time.perf_counter()
                pools[k] = query(collection, vector, k)
                times[k] = (time.perf_counter()-started)*1000
            def add(name, chunks, elapsed, pool_size):
                row['variants'][name] = {'metrics': metrics(chunks, q['expected_articles']),
                                         'chunk_ids': [c['chunk_id'] for c in chunks],
                                         'articles': [[c['source_document'], c['article']] for c in chunks],
                                         'distances': [c['distance'] for c in chunks],
                                         'retrieval_ms': elapsed, 'candidate_count': pool_size}
            add('baseline10', pools[10], times[10], len(pools[10]))
            for k in (20, 50):
                add(f'pool{k}', pools[k], times[k], len(pools[k]))
                started = time.perf_counter(); selected = filter_candidates(pools[k], regime)
                add(f'postfilter{k}_top10', selected[:10], times[k]+(time.perf_counter()-started)*1000, len(pools[k]))
                started = time.perf_counter(); selected = reranker.rerank(question, pools[k])
                add(f'rrf{k}_top10', selected[:10], times[k]+(time.perf_counter()-started)*1000, len(pools[k]))
            started = time.perf_counter(); selected = reranker.rerank(question, filter_candidates(pools[50], regime))
            add('postfilter_rrf50_top10', selected[:10], times[50]+(time.perf_counter()-started)*1000, len(pools[50]))
            for k in (10, 50):
                started = time.perf_counter()
                selected = query(collection, vector, k, regime) if regime != 'unspecified' else pools[k]
                elapsed = (time.perf_counter()-started)*1000 if regime != 'unspecified' else times[k]
                if k == 10:
                    add('prefilter10', selected, elapsed, len(selected))
                else:
                    add('prefilter50', selected, elapsed, len(selected))
                    started = time.perf_counter(); reranked = reranker.rerank(question, selected)
                    add('prefilter_rrf50_top10', reranked[:10], elapsed+(time.perf_counter()-started)*1000, len(selected))
            row['depth_top10_order_stable'] = all([c['chunk_id'] for c in pools[10]] == [c['chunk_id'] for c in pools[k][:10]] for k in (20, 50))
            if q['id'] in MISS_IDS:
                deep = query(collection, vector, len(stored))
                expected = {key(a) for a in q['expected_articles']}
                exact = exact_ranks(vector, stored, batch['embeddings'])
                row['diagnostics'] = diagnose(q, deep, stored)
                row['diagnostics']['exact_cosine_expected_ranks'] = [i for i, c in enumerate(exact, 1) if key(c) in expected]
                row['diagnostics']['top10_sources'] = dict(Counter(c['source_document'] for c in pools[10]))
                row['diagnostics']['rank10_distance'] = pools[10][-1]['distance']
                row['diagnostics']['expected_chunks'] = [dict(c, dense_rank=i, bm25_score=reranker.score(question, c))
                                                        for i, c in enumerate(deep, 1) if key(c) in expected]
                row['diagnostics']['top10'] = pools[10]
            rows.append(row)
            write_new_json(root / 'cases' / (q['id'] + '.json'), row)
        after = index_fingerprint(retriever.client)
    finally:
        retriever.client.close(); retriever.client = None; retriever.client_path = None
    retriever.get_collection()
    try:
        reopened = index_fingerprint(retriever.client)
    finally:
        retriever.client.close()
    write_new_json(root / 'worker-results.json', {
        'config': CONFIG, 'rows': rows, 'summary': compare(rows), 'fingerprints': fingerprints,
        'model_load_seconds': model_load_seconds, 'api_requests': 0,
        'isolation': {'opened_paths': sorted(set(opened)), 'snapshot_byte_match': True,
                      'logical_differences': logical_differences(before, after),
                      'reopen_differences': logical_differences(before, reopened)}})


def run(output):
    output = require_new_output(output)
    if not disjoint(output) or not disjoint(Path(tempfile.gettempdir())):
        raise ValueError('Experiment storage must be outside the protected index')
    root = Path(tempfile.mkdtemp(prefix='compliance-rag-experiments-'))
    print(f'Isolated offline workspace: {root}', flush=True)
    result = {'status': 'blocked', 'workspace': str(root), 'api_requests': 0}
    with locked_snapshot(PROTECTED_INDEX) as snapshot:
        before = snapshot.hashes()
        write_new_json(root / 'source-baseline.json', {'source': str(PROTECTED_INDEX), 'hashes': before})
        snapshot.copy_to(root / 'working')
        try:
            process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root)],
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
            if not process.returncode:
                result.update(json.loads((root / 'worker-results.json').read_text(encoding='utf-8')))
                result['status'] = 'completed' if not result['isolation']['logical_differences'] and not result['isolation']['reopen_differences'] else 'integrity_failure'
            else:
                result['worker_exit'] = process.returncode
        finally:
            result['original_hashes_unchanged'] = snapshot.hashes() == before
        if not result['original_hashes_unchanged']:
            result['status'] = 'integrity_failure'
    write_new_json(output, result)
    print(f"Status: {result['status']}; original unchanged: {result['original_hashes_unchanged']}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--replay-input', type=Path, help='Replay scoped follow-up from saved isolated candidates; no index opened')
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
            result = replay_scoped(args.replay_input, args.output) if args.replay_input else run(args.output)
        except (ValueError, RuntimeError, FileExistsError) as exc:
            parser.error(str(exc))
        if result['status'] != 'completed':
            raise SystemExit(2)


if __name__ == '__main__':
    main()
