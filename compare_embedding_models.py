"""Benchmark MiniLM, MPNet, and BGE retrieval on the same legal-law chunks.

Run from the project directory:
    python compare_embedding_models.py --limit 3
    python compare_embedding_models.py

Only two NEW collections are created or updated. Existing 'compliance_docs'
(MiniLM) is read-only in this script; Streamlit is not modified.
"""

import argparse
import json
import time
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = Path('data/chunks.json')
EVAL_FILE = Path('rag_evaluation_20_questions.json')
DB_PATH = 'data/chroma_db'
OUTPUT_FILE = Path('embedding_comparison_results.json')

BASELINE_COLLECTION = 'compliance_docs'
CANDIDATES = {
    'MPNet': {
        'model': 'sentence-transformers/all-mpnet-base-v2',
        'collection': 'compliance_mpnet',
        'query_prefix': '',
    },
    'BGE': {
        'model': 'BAAI/bge-base-en-v1.5',
        'collection': 'compliance_bge',
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


def rebuild_candidate_collection(client, name, chunks, ids, embeddings):
    # Generate and validate the embeddings BEFORE replacing a test collection.
    if len(embeddings) != len(chunks):
        raise ValueError('Embeddings/chunks length mismatch')
    existing = [c.name if hasattr(c, 'name') else c for c in client.list_collections()]
    if name in existing:
        client.delete_collection(name)
    collection = client.create_collection(name=name, metadata={'hnsw:space': 'cosine'})
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
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.top_k < 10:
        parser.error('--top-k must be >= 10 to report Hit@10')

    chunks = load_json(CHUNKS_FILE)
    ids = validate_chunks(chunks)
    questions = load_json(EVAL_FILE)
    if args.limit is not None:
        questions = questions[:args.limit]
    if not questions:
        raise ValueError('No evaluation questions')

    client = chromadb.PersistentClient(path=DB_PATH)
    baseline = client.get_collection(BASELINE_COLLECTION)
    if baseline.count() != len(chunks):
        raise ValueError(
            f'Baseline has {baseline.count()} records, but chunks.json has {len(chunks)}. '
            'Check that you are using the corresponding dataset before comparing.'
        )
    print(f'Loaded {len(chunks)} chunks, {len(questions)} questions.')
    print('Existing MiniLM collection will NOT be modified.\n')

    # First evaluate MiniLM, without replacing/rebuilding its current collection.
    print('=== MiniLM (existing baseline) ===')
    baseline_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
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
        collection = rebuild_candidate_collection(client, config['collection'], chunks, ids, embeddings)
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

    OUTPUT_FILE.write_text(json.dumps({
        'total_questions': len(questions),
        'chunks': len(chunks),
        'top_k': args.top_k,
        'note': 'Metrics are retrieval-only. OOS questions are not graded without a relevance gate. Do not compare raw distances across indexes.',
        'results': results,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nSaved: {OUTPUT_FILE}')
    print('No changes were made to compliance_docs, generate_answer.py, or app.py.')


if __name__ == '__main__':
    main()
