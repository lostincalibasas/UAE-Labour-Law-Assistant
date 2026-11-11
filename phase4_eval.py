"""Controlled evaluation using Phase 3.5 snapshots; APIs opt in via separate budgets."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from artifact_io import require_new_output, write_new_json
from evidence_citations import build_evidence, resolve_answer
from index_integrity import digest, index_fingerprint, logical_differences
from index_isolation import locked_snapshot, tree_hashes, install_chroma_guard
from index_paths import PROTECTED_INDEX, disjoint, resolve_index_path
from eval_report import make_report, markdown

BASE = Path(__file__).resolve().parent
MISSES = {'Q027', 'Q041', 'Q068', 'Q072'}


class Budget:
    def __init__(self, limit):
        if type(limit) is not int or limit < 0:
            raise ValueError('Request budget must be a nonnegative integer')
        self.limit, self.used = limit, 0

    def consume(self):
        if self.used >= self.limit:
            raise RuntimeError('request_budget_exhausted')
        self.used += 1


def select_questions(questions, ids):
    known = {q['id']: q for q in questions}
    if len(known) != len(questions) or not ids or len(ids) != len(set(ids)):
        raise ValueError('Question IDs must be explicit and unique (or use --ids all)')
    if ids == ['all']:
        return questions
    if any(i not in known for i in ids):
        raise ValueError('Unknown question ID')
    return [known[i] for i in ids]


def fingerprint_files():
    from generate_answer import SYSTEM_PROMPT, MODEL, API_TIMEOUT_SECONDS
    from eval_judge import JUDGE_PROMPT
    from retrieve_bge import MODEL_NAME, QUERY_PREFIX
    files = ['data/eval_set.json', 'data/chunks.json', 'generate_answer.py', 'retrieve_bge.py',
             'evidence_citations.py', 'eval_answers.py', 'eval_judge.py', 'phase4_eval.py', 'eval_report.py']
    versions = {}
    for package in ('chromadb', 'sentence-transformers', 'transformers', 'torch', 'openai'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    model_revision = None
    try:
        from huggingface_hub import try_to_load_from_cache
        config = try_to_load_from_cache(MODEL_NAME, 'config.json')
        if isinstance(config, str):
            model_revision = Path(config).parent.name
    except Exception:
        pass
    return {'files_sha256': {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest() for name in files},
            'embedding': {'model': MODEL_NAME, 'cached_revision': model_revision, 'query_prefix': QUERY_PREFIX,
                          'normalize_embeddings': True, 'distance': 'cosine'},
            'generation': {'model': MODEL, 'max_tokens': 1000, 'temperature': 'provider_default',
                           'timeout_seconds': API_TIMEOUT_SECONDS, 'max_retries': 0},
            'judge': {'model': os.environ.get('JUDGE_MODEL'), 'temperature': 0, 'timeout_seconds': 30, 'max_retries': 0},
            'generation_prompt_sha256': digest(SYSTEM_PROMPT), 'judge_prompt_sha256': digest(JUDGE_PROMPT),
            'packages': versions, 'python': sys.version.split()[0]}


def diagnose(q, ranked, stored):
    from eval_answers import key, norm, _merge
    expected = {key(a) for a in q['expected_articles']}
    matches = [{'rank': i, 'source_document': c['source_document'], 'article': c['article'],
                'distance': c['distance'], 'text_sha256': digest(c['text'])}
               for i, c in enumerate(ranked, 1) if key(c) in expected]
    facts = []
    for i, fact in enumerate(q['must_include']):
        if not fact.get('quote'):
            continue
        article_chunks = [c for c in stored if key(c) == key(fact)]
        article_chunks.sort(key=lambda c: (0, int(c['chunk_id'])) if str(c['chunk_id']).isdigit() else (1, str(c['chunk_id'])))
        quote = norm(fact['quote'])
        merged = ''
        for c in article_chunks:
            body = c['text'].split('\n', 1)[-1]
            merged = _merge(merged, norm(body))
        facts.append({'fact_id': i,
                      'single_chunk_ids': [c['chunk_id'] for c in article_chunks if quote in norm(c['text'])],
                      'reconstructed_article_contains_quote': quote in merged,
                      'retrieved_top10_contains_quote': any(quote in norm(c['text']) and key(c) == key(fact) for c in ranked[:10]),
                      'article_chunks': [{'chunk_id': c['chunk_id'], 'characters': len(c['text']),
                                          'text_sha256': digest(c['text'])} for c in article_chunks]})
    return {'retrieval_depth': len(ranked), 'expected_article_ranks': matches,
            'quote_boundary_checks': facts, 'human_answer_key_review': q['id'] in {'Q041', 'Q068'},
            'note': 'Ranks use one deeper diagnostic query; production ranking algorithm unchanged. Quote checks are text matching, not semantic entailment.'}


def evaluate_questions(questions, config, retrieve, generate, judge, checkpoint=None, stored=None):
    """Pure orchestration boundary: dependencies injected in offline regression tests."""
    import eval_answers as evaluation
    generation_budget, judge_budget = Budget(config['generation_budget']), Budget(config['judge_budget'])
    rows = []
    for q in questions:
        row = {'id': q['id'], 'answerable': q['answerable'], 'category': q['category'],
               'retrieval': {}, 'claim_support': 'not_evaluated'}
        depth = max(config['ks'])
        if config['diagnostics'] and q['id'] in MISSES:
            depth = max(depth, 252)
        started = time.perf_counter()
        try:
            ranked = retrieve(q['question'], top_k=depth)  # Exactly once per question.
        except Exception as exc:
            from rag_errors import RAGError
            row['retrieval_error'] = exc.code if isinstance(exc, RAGError) else 'retrieval_unavailable'
            ranked = None
        row['retrieval_seconds'] = round(time.perf_counter() - started, 4)
        if ranked is not None:
            row['ranked_chunks'] = ranked
            evidence = build_evidence(ranked[:config['answer_k']])
            row['evidence'] = evidence
            row['evidence_sha256'] = digest(evidence)
            for k in config['ks']:
                if q['expected_articles']:
                    row['retrieval'][str(k)] = evaluation.retrieval_metrics(ranked, q['expected_articles'], k)
            if config['diagnostics'] and q['id'] in MISSES:
                row['diagnostics'] = diagnose(q, ranked, stored or [])
            if config['mode'] == 'answers':
                if generation_budget.used >= generation_budget.limit:
                    row['generation_skipped'] = 'request_budget_exhausted'
                else:
                    started = time.perf_counter()
                    try:
                        response = generate(q['question'], config['answer_k'], include_evidence=True,
                                            evidence=evidence, before_request=generation_budget.consume)
                    except Exception:
                        from rag_errors import operational_failure, RAGError
                        response = operational_failure(RAGError('internal_error', 'evaluation'))
                    row['generation_seconds'] = round(time.perf_counter() - started, 4)
                    if digest(evidence) != row['evidence_sha256']:
                        raise RuntimeError('Captured evidence changed during generation')
                    # Recheck exact metadata/excerpts using the captured context.
                    if response['status'] == 'ok':
                        checked = resolve_answer(response['answer'], evidence)
                        if checked['citations'] != response.get('citations') or checked['status'] != 'ok':
                            response = resolve_answer('', evidence)
                            response['citation_validation']['status'] = 'invalid_citations'
                    row['response'] = response
                    row['citations'] = evaluation.citation_check(response['answer'], q, response.get('citations', []))
                    if (not config['no_judge'] and response['status'] != 'operational_error'
                            and response['citation_validation']['status'] not in {'invalid_citations', 'missing_citations'}):
                        if judge_budget.used >= judge_budget.limit:
                            row['judge_skipped'] = 'request_budget_exhausted'
                        else:
                            started = time.perf_counter()
                            row['judge'] = judge(q, response['answer'], evidence, before_request=judge_budget.consume)
                            row['judge_seconds'] = round(time.perf_counter() - started, 4)
                            if digest(evidence) != row['evidence_sha256']:
                                raise RuntimeError('Captured evidence changed during judging')
                            if row['judge'].get('status') == 'valid':
                                row['claim_support'] = 'judge_assessed'  # Never changes production response.
        row['requests_so_far'] = {'generation': generation_budget.used, 'judge': judge_budget.used}
        rows.append(row)
        if checkpoint:
            checkpoint(row)
        print(f"{q['id']}: captured" if ranked is not None else f"{q['id']}: retrieval failure", flush=True)
    return {'rows': rows, 'requests': {'generation': generation_budget.used, 'judge': judge_budget.used}}


def worker(root):
    root = Path(root).resolve()
    config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'source-baseline.json').read_text(encoding='utf-8'))
    target = root / 'working'
    if not disjoint(root) or not disjoint(root, manifest['source']) or tree_hashes(target) != manifest['hashes']:
        raise RuntimeError('Unverified or unsafe snapshot')
    os.environ.update(RAG_TEST_INDEX_ROOT=str(root), RAG_INDEX_PATH=str(target), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
    if resolve_index_path() != target:
        raise RuntimeError('Index path mismatch')
    opened = install_chroma_guard(target)
    import retrieve_bge
    import eval_answers as evaluation
    collection = retrieve_bge.get_collection()
    before = index_fingerprint(retrieve_bge.client)
    # Inspect exact stored text/metadata in the isolated DB for boundary diagnostics.
    batch = collection.get(include=['documents', 'metadatas'])
    stored = [dict(m, text=t, chunk_id=i) for i, t, m in zip(batch['ids'], batch['documents'], batch['metadatas'])]
    questions = select_questions(evaluation.load_eval_set(), config['ids'])
    fingerprints = fingerprint_files()
    fingerprints['index_logical_sha256'] = digest(before)
    fingerprints['index_files_sha256'] = digest(manifest['hashes'])
    fingerprints['evaluation_config_sha256'] = digest(config)
    fingerprints['stored_chunks_match_export'] = (
        sorted((digest(c['text']), c['source_document'], c['article']) for c in stored) ==
        sorted((digest(c['text']), c['source_document'], c['article']) for c in json.loads(evaluation.CHUNKS.read_text(encoding='utf-8'))))
    try:
        result = evaluate_questions(questions, config, retrieve_bge.retrieve_chunks,
                                    evaluation.generate_answer, evaluation.judge_answer,
                                    checkpoint=lambda row: write_new_json(root / 'cases' / (row['id'] + '.json'), row), stored=stored)
        after = index_fingerprint(retrieve_bge.client)
    finally:
        retrieve_bge.client.close()
        retrieve_bge.client = None
        retrieve_bge.client_path = None
    # Also check logical stability after native close/reopen.
    retrieve_bge.get_collection()
    try:
        reopened = index_fingerprint(retrieve_bge.client)
    finally:
        retrieve_bge.client.close()
    result.update(schema_version=1, config=config, fingerprints=fingerprints,
                  isolation={'opened_paths': sorted(set(opened)), 'snapshot_byte_match': True,
                             'logical_differences': logical_differences(before, after),
                             'reopen_differences': logical_differences(before, reopened)})
    write_new_json(root / 'worker-results.json', result)


def run(config, output):
    output = require_new_output(output)
    if not disjoint(output) or not disjoint(Path(tempfile.gettempdir())):
        raise ValueError('Output and temporary storage must be outside protected indexes')
    root = Path(tempfile.mkdtemp(prefix='compliance-rag-eval-'))
    print(f'Isolated workspace: {root}', flush=True)
    write_new_json(root / 'config.json', config)
    with locked_snapshot(PROTECTED_INDEX) as snapshot:
        before = snapshot.hashes()
        write_new_json(root / 'source-baseline.json', {'source': str(PROTECTED_INDEX), 'hashes': before})
        snapshot.copy_to(root / 'working')
        try:
            process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '_worker', str(root)],
                                     env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
            if process.returncode:
                # Do not expose provider errors, queries or passages in logs.
                result = {'status': 'blocked', 'workspace': str(root), 'worker_exit': process.returncode}
            else:
                result = json.loads((root / 'worker-results.json').read_text(encoding='utf-8'))
                result['workspace'] = str(root)
                integrity = result['isolation']
                result['status'] = 'completed' if not integrity['logical_differences'] and not integrity['reopen_differences'] else 'integrity_failure'
        finally:
            unchanged = snapshot.hashes() == before
        result['original_hashes_unchanged'] = unchanged
        if not unchanged:
            result['status'] = 'integrity_failure'
    write_new_json(output, result)
    if 'rows' in result:
        report = make_report(result)
        write_new_json(root / 'report.json', report)
        with (root / 'report.md').open('x', encoding='utf-8') as file:
            file.write(markdown(report))
        print(f"Report: {root / 'report.md'}", flush=True)
    print(f"Status: {result['status']}; original hashes unchanged: {unchanged}", flush=True)
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '_worker':
        try:
            worker(Path(argv[1]))
        except Exception as exc:
            # Safe diagnostic only; partial per-question records remain available.
            write_new_json(Path(argv[1]) / 'failure.json', {'type': type(exc).__name__, 'code': getattr(exc, 'code', 'worker_failure')})
            raise SystemExit(2)
        return
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['retrieval', 'answers', 'report'])
    p.add_argument('--ids', nargs='+', help='Explicit IDs in execution order, or all')
    p.add_argument('--k', nargs='+', type=int, default=[1, 3, 5, 10])
    p.add_argument('--answer-k', type=int, default=10)
    p.add_argument('--generation-budget', type=int, default=0)
    p.add_argument('--judge-budget', type=int, default=0)
    p.add_argument('--no-judge', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--diagnostics', action='store_true')
    p.add_argument('--input', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        require_new_output(args.output)
        if not disjoint(args.output):
            raise ValueError('Output overlaps protected index')
        if args.mode == 'report':
            if not args.input:
                raise ValueError('--input is required for report')
            report = make_report(json.loads(args.input.read_text(encoding='utf-8')))
            write_new_json(args.output, report)
            return
        from eval_answers import load_eval_set
        questions = select_questions(load_eval_set(), args.ids)
        if any(k < 1 for k in args.k) or args.answer_k < 1:
            raise ValueError('K must be positive')
        Budget(args.generation_budget); Budget(args.judge_budget)
        if args.mode == 'retrieval' and (args.generation_budget or args.judge_budget):
            raise ValueError('Retrieval mode requires zero API budgets')
        if args.no_judge and args.judge_budget:
            raise ValueError('--no-judge requires zero judge budget')
        config = {'mode': args.mode, 'ids': [q['id'] for q in questions],
                  'ks': sorted(set(args.k + [args.answer_k])), 'answer_k': args.answer_k,
                  'generation_budget': args.generation_budget, 'judge_budget': args.judge_budget,
                  'no_judge': args.no_judge, 'diagnostics': args.diagnostics}
        if args.dry_run:
            write_new_json(args.output, {'dry_run': True, 'config': config, 'fingerprints': fingerprint_files(),
                                        'max_generation_requests': min(len(questions), args.generation_budget) if args.mode == 'answers' else 0,
                                        'max_judge_requests': min(len(questions), args.judge_budget) if args.mode == 'answers' and args.generation_budget else 0,
                                        'actual_requests': 0, 'index_opened': False})
        else:
            result = run(config, args.output)
            if result['status'] != 'completed':
                raise SystemExit(2)
    except (ValueError, FileExistsError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == '__main__':
    main()
