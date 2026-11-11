"""Benchmark MiniLM, MPNet, and BGE retrieval on the same legal-law chunks.

Run from the project directory:
    python compare_embedding_models.py --limit 3
    python compare_embedding_models.py

All three models are indexed in a new benchmark database. The active database
is never opened. Existing database directories and result files are refused.
"""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from artifact_io import require_new_output, write_new_json

BASE_DIR = Path(__file__).resolve().parent
CHUNKS_FILE = BASE_DIR / 'data' / 'chunks.json'
EVAL_FILE = BASE_DIR / 'rag_evaluation_20_questions.json'
DB_PATH = BASE_DIR / 'data' / 'chroma_db'
OUTPUT_FILE = BASE_DIR / 'embedding_comparison_results.json'

BASELINE_COLLECTION = 'benchmark_minilm'
CANDIDATES = {
    'MPNet': {
        'model': 'sentence-transformers/all-mpnet-base-v2',
        'collection': 'benchmark_mpnet',
        'query_prefix': '',
    },
    'BGE': {
        'model': 'BAAI/bge-base-en-v1.5',
        'collection': 'benchmark_bge',
        # BGE's retrieval-specific query instruction; passages are unprefixed.
        'query_prefix': 'Represent this sentence for searching relevant passages: ',
    },
}


def load_json(path):
    with path.open(encoding='utf-8') as file:
        return json.load(file)


def validate_chunks(chunks):
    if not chunks:
        raise ValueError('No chunks found. Run chunk_text.py first.')
    ids = [str(c['chunk_id']) for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate chunk IDs in chunks.json')
    for c in chunks:
        for key in ('text', 'source_document', 'filename', 'article'):
            if not c.get(key):
                raise ValueError(f'Missing or empty {key} in chunk {c.get("chunk_id")}')
    return ids


def create_candidate_collection(client, name, chunks, ids, embeddings, space='cosine'):
    # create_collection refuses collisions; never delete or reuse a collection.
    if len(embeddings) != len(chunks):
        raise ValueError('Embeddings/chunks length mismatch')
    collection = client.create_collection(name=name, metadata={'hnsw:space': space})
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=[c['text'] for c in chunks],
        metadatas=[
            {'source_document': c['source_document'],
             'filename': c['filename'],
             'article': c['article']}
            for c in chunks
        ],
    )
    if collection.count() != len(chunks):
        raise RuntimeError(f'{name}: expected {len(chunks)} records, got {collection.count()}')
    return collection


def prepare_benchmark_directory(path):
    path = Path(path).resolve()
    active = Path(DB_PATH).resolve()
    if path == active or active in path.parents or path in active.parents:
        raise ValueError('Benchmark database must be separate from the active database.')
    # A fresh directory prevents collisions with any previous benchmark or index.
    path.mkdir(parents=True, exist_ok=False)
    return path


def search(collection, embedding, top_k):
    result = collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, collection.count()),
        include=['metadatas', 'distances'],
    )
    return [
        {
            'source_document': m['source_document'],
            'article': m.get('article', 'unknown'),
            'distance': float(d),
        }
        for m, d in zip(result['metadatas'][0], result['distances'][0])
    ]


def evaluate_model(label, model, collection, questions, top_k, prefix='', normalize_query=True):
    details = []
    ranks = []
    started = time.perf_counter()

    for item in questions:
        query = prefix + item['question']
        embedding = model.encode(query, normalize_embeddings=normalize_query).tolist()
        results = search(collection, embedding, top_k)
        expected_source = item.get('expected_source_document')
        expected_article = item.get('expected_article')
        rank = None
        if item.get('answerable') and expected_source and expected_article:
            rank = next((idx for idx, hit in enumerate(results, 1)
                         if hit['source_document'] == expected_source
                         and hit['article'] == expected_article), None)
            ranks.append(rank)
        details.append({
            'id': item['id'],
            'question': item['question'],
            'answerable': item['answerable'],
            'expected_source_document': expected_source,
            'expected_article': expected_article,
            'expected_rank': rank,
            'top_results': results,
        })
        if item.get('answerable'):
            print(f'  {item["id"]}: expected article rank {rank if rank else "not in top " + str(top_k)}')
        else:
            print(f'  {item["id"]}: out of scope (no automatic retrieval correctness score)')

    n = len(ranks)
    metrics = {
        'answerable_test_count': n,
        'hit_at_1': round(sum(r is not None and r <= 1 for r in ranks) / n, 4) if n else None,
        'hit_at_5': round(sum(r is not None and r <= 5 for r in ranks) / n, 4) if n else None,
        'hit_at_10': round(sum(r is not None and r <= 10 for r in ranks) / n, 4) if n else None,
        'mrr_at_10': round(sum(1 / r if r is not None and r <= 10 else 0 for r in ranks) / n, 4) if n else None,
        'query_seconds_total': round(time.perf_counter() - started, 2),
    }
    return {'model': label, 'metrics': metrics, 'questions': details}


def main():
    parser = argparse.ArgumentParser(description='Compare MiniLM vs MPNet and BGE on legal chunk retrieval.')
    parser.add_argument('--limit', type=int, default=None, help='Use the first N evaluation questions')
    parser.add_argument('--top-k', type=int, default=10, help='Number of retrieved chunks (default 10)')
    parser.add_argument('--output', type=Path, default=OUTPUT_FILE,
                        help='New results file; existing files are never overwritten')
    parser.add_argument('--db-path', type=Path,
                        default=BASE_DIR / 'data' / 'benchmarks' / uuid4().hex,
                        help='New isolated database directory (default: unique data/benchmarks directory)')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.top_k < 10:
        parser.error('--top-k must be >= 10 to report Hit@10')
    try:
        require_new_output(args.output)
    except FileExistsError as exc:
        parser.error(str(exc))

    chunks = load_json(CHUNKS_FILE)
    ids = validate_chunks(chunks)
    questions = load_json(EVAL_FILE)
    if args.limit is not None:
        questions = questions[:args.limit]
    if not questions:
        raise ValueError('No evaluation questions')

    try:
        benchmark_path = prepare_benchmark_directory(args.db_path)
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=str(benchmark_path))
    print(f'Loaded {len(chunks)} chunks, {len(questions)} questions.')
    print(f'Isolated benchmark database: {benchmark_path}\n')

    # Match the original MiniLM builder: unnormalized embeddings, L2 distance.
    print('=== MiniLM (isolated baseline) ===')
    baseline_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    baseline_embeddings = baseline_model.encode(
        [chunk['text'] for chunk in chunks], show_progress_bar=True,
        normalize_embeddings=False,
    ).tolist()
    baseline = create_candidate_collection(
        client, BASELINE_COLLECTION, chunks, ids, baseline_embeddings, space='l2',
    )
    results = {'MiniLM': evaluate_model('MiniLM', baseline_model, baseline, questions, args.top_k, normalize_query=False)}
    del baseline_model

    # Then build two independent cosine-distance indexes and evaluate them.
    for label, config in CANDIDATES.items():
        print(f'\n=== {label}: {config["model"]} ===')
        model = SentenceTransformer(config['model'])
        texts = [chunk['text'] for chunk in chunks]
        started = time.perf_counter()
        embeddings = model.encode(texts, batch_size=32, show_progress_bar=True,
                                  normalize_embeddings=True).tolist()
        build_time = round(time.perf_counter() - started, 2)
        collection = create_candidate_collection(client, config['collection'], chunks, ids, embeddings)
        print(f'Built {collection.name} with {collection.count()} chunks in {build_time}s')
        result = evaluate_model(label, model, collection, questions, args.top_k,
                                prefix=config['query_prefix'])
        result['index_embedding_seconds'] = build_time
        results[label] = result
        del model

    print('\n=== RETRIEVAL COMPARISON (answerable questions only) ===')
    print(f'{"Model":<12} {"Hit@1":>8} {"Hit@5":>8} {"Hit@10":>8} {"MRR@10":>8}')
    for label, result in results.items():
        m = result['metrics']
        print(f'{label:<12} {m["hit_at_1"]:>8.1%} {m["hit_at_5"]:>8.1%} '
              f'{m["hit_at_10"]:>8.1%} {m["mrr_at_10"]:>8.3f}')

    write_new_json(args.output, {
        'total_questions': len(questions),
        'chunks': len(chunks),
        'top_k': args.top_k,
        'benchmark_db_path': str(benchmark_path),
        'baseline': 'MiniLM rebuilt in isolation using unnormalized embeddings and L2 distance',
        'note': 'Metrics are retrieval-only. OOS questions are not graded without a relevance gate. Do not compare raw distances across indexes.',
        'results': results,
    })
    print(f'\nSaved: {args.output}')
    print('The active ChromaDB database was not opened or modified.')


if __name__ == '__main__':
    main()
