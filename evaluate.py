"""Evaluate the UAE labour-law RAG project with a fixed 20-question dataset.

Run from the project directory:
    python evaluate.py --limit 3
    python evaluate.py
    python evaluate.py --retrieval-only
    python evaluate.py --limit 3 --verbose

This script does not modify ChromaDB or the RAG pipeline.
It makes one LLM call per question unless --retrieval-only is used.
"""

import argparse
import contextlib
import io
import json
from pathlib import Path

from retrieve_bge import retrieve_chunks

FALLBACK = (
    "I don't have enough information in the available documents "
    "to answer this confidently."
)
TOP_K = 10
BASE_DIR = Path(__file__).resolve().parent


def metric(passed, total):
    return {
        "passed": passed,
        "total": total,
        "percentage": round(100 * passed / total, 1) if total else None,
    }


def evaluate_case(case, generate_answer=None, verbose=False):
    """Check retrieval and optionally generation for one ground-truth record."""
    expected_document = case["expected_source_document"]
    expected_article = case["expected_article"]
    answerable = case["answerable"]

    result = {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answerable": answerable,
        "expected_source_document": expected_document,
        "expected_article": expected_article,
        "expected_key_facts": case["expected_key_facts"],
        "retrieval_hit_at_10": None,
        "retrieval_rank": None,
        "retrieved_chunks": [],
        "answer": None,
        "sources": [],
        "citation_hit": None,
        "fallback_pass": None,
        "answer_correct": None,
        "citation_correct": None,
        "notes": "",
        "error": None,
    }

    try:
        chunks = retrieve_chunks(case["question"], top_k=TOP_K)
        for rank, chunk in enumerate(chunks[:TOP_K], start=1):
            result["retrieved_chunks"].append({
                "rank": rank,
                "source_document": chunk.get("source_document"),
                "article": chunk.get("article"),
                "distance": chunk.get("distance"),
                "preview": chunk.get("text", "")[:160],
            })

        if answerable:
            ranks = [
                i + 1 for i, chunk in enumerate(chunks[:TOP_K])
                if chunk.get("source_document") == expected_document
                and chunk.get("article") == expected_article
            ]
            result["retrieval_hit_at_10"] = bool(ranks)
            result["retrieval_rank"] = ranks[0] if ranks else None

    except Exception as exc:
        result["error"] = f"Retrieval: {type(exc).__name__}: {exc}"
        return result

    if generate_answer is None:
        return result

    try:
        if verbose:
            generated = generate_answer(case["question"], top_k=TOP_K)
        else:
            # Silence debug print() statements in generate_answer.py during evaluation.
            # Only stdout is suppressed, not error messages on stderr.
            with contextlib.redirect_stdout(io.StringIO()):
                generated = generate_answer(case["question"], top_k=TOP_K)
        answer = (generated.get("answer") or "").strip()
        sources = generated.get("sources") or []
        result["answer"] = answer
        result["sources"] = sources

        if answerable:
            # Citation presence is not the same as factual correctness.
            expected_citation = f"{expected_document} — {expected_article}"
            result["citation_hit"] = expected_citation in sources
        else:
            result["fallback_pass"] = (answer.startswith(FALLBACK)and len(sources) == 0)

    except Exception as exc:
        result["error"] = f"Generation: {type(exc).__name__}: {exc}"

    return result


def summarize(results, retrieval_only):
    answerable = [r for r in results if r["answerable"]]
    out_of_scope = [r for r in results if not r["answerable"]]
    summary = {
        "questions_run": len(results),
        "answerable_run": len(answerable),
        "out_of_scope_run": len(out_of_scope),
        "errors": sum(bool(r["error"]) for r in results),
        "retrieval_hit_at_10": metric(
            sum(r["retrieval_hit_at_10"] is True for r in answerable),
            len(answerable),
        ),
    }
    if not retrieval_only:
        summary["expected_article_citation_hit"] = metric(
            sum(r["citation_hit"] is True for r in answerable),
            len(answerable),
        )
        summary["out_of_scope_fallback_pass"] = metric(
            sum(r["fallback_pass"] is True for r in out_of_scope),
            len(out_of_scope),
        )
    summary["manual_review_pending"] = (
        sum(r["answer_correct"] is None and r["answerable"] for r in results)
        if not retrieval_only else None
    )
    return summary


def format_metric(label, score):
    pct = f"{score['percentage']:.1f}%" if score["percentage"] is not None else "N/A"
    return f"{label:<24} {score['passed']:>2}/{score['total']:<2}  ({pct})"


def main():
    parser = argparse.ArgumentParser(description="Evaluate UAE labour-law RAG")
    parser.add_argument(
        "--dataset", type=Path,
        default=BASE_DIR / "rag_evaluation_20_questions.json",
        help="Input dataset JSON (default: next to evaluate.py)",
    )
    parser.add_argument(
        "--output", type=Path,
        default=BASE_DIR / "evaluation_results.json",
        help="Where to write detailed results",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run only the first N tests",
    )
    parser.add_argument(
        "--retrieval-only", action="store_true",
        help="Skip DeepSeek calls and test only retrieval",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show generate_answer.py debug output",
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")

    with args.dataset.open("r", encoding="utf-8") as file:
        cases = json.load(file)
    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset must be a non-empty JSON list")

    cases = cases[:args.limit] if args.limit is not None else cases
    generate_answer = None
    if not args.retrieval_only:
        from generate_answer import generate_answer

    print(f"\nUAE LABOUR LAW RAG — EVALUATION")
    print(f"Retriever: BGE | Collection: compliance_bge | Top-K: {TOP_K}")
    print(f"Questions: {len(cases)} | Mode: {'retrieval only' if args.retrieval_only else 'retrieval + generation'}")
    print("-" * 76)

    results = []
    for index, case in enumerate(cases, start=1):
        result = evaluate_case(case, generate_answer, verbose=args.verbose)
        results.append(result)
        identifier = f"[{index:>2}/{len(cases)}] {case['id']}"
        if result["error"]:
            status = f"ERROR: {result['error']}"
        elif case["answerable"]:
            retrieval = f"retrieval={'PASS' if result['retrieval_hit_at_10'] else 'FAIL'}"
            rank = f"rank=#{result['retrieval_rank']}" if result["retrieval_rank"] is not None else "rank=—"
            status = f"{retrieval:<16} {rank:<10}"
            if not args.retrieval_only:
                status += f"  citation={'PASS' if result['citation_hit'] else 'FAIL'}"
        else:
            status = "out-of-scope"
            if not args.retrieval_only:
                status += f"  fallback={'PASS' if result['fallback_pass'] else 'FAIL'}"
        print(f"{identifier:<14} {status}", flush=True)

    summary = summarize(results, args.retrieval_only)
    report = {
        "settings": {
            "retriever": "BGE",
            "collection": "compliance_bge",
            "top_k": TOP_K,
            "retrieval_only": args.retrieval_only,
            "dataset": str(args.dataset),
        },
        "summary": summary,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("-" * 76)
    print("SUMMARY")
    print(f"Questions: {summary['questions_run']}  |  Errors: {summary['errors']}")
    print(format_metric("Retrieval Hit@10", summary["retrieval_hit_at_10"]))
    if not args.retrieval_only:
        print(format_metric("Expected citation", summary["expected_article_citation_hit"]))
        print(format_metric("Out-of-scope fallback", summary["out_of_scope_fallback_pass"]))
        print("Answer correctness: manual review required")
    print(f"Detailed report: {args.output}")


if __name__ == "__main__":
    main()
