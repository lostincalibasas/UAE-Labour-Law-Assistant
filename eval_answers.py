"""RAG evaluation: retrieval metrics + citation check + LLM-judged answer correctness.

Commands (run from the compliance-rag project root, next to data/chunks.json):

  python eval_answers.py verify-set                 # check every quote exists in chunks.json under its article
  python eval_answers.py retrieval --ids all --output runs/new.json  # isolated, no APIs
  python eval_answers.py answers --ids Q001 --dry-run --output runs/plan.json
  python eval_answers.py audit --n 25               # hand-check judge verdicts, get agreement rate

Needs for `answers`:
  Explicit nonzero generation/judge budgets to authorize request attempts;
  defaults are zero. All retrieval CLI commands use Phase 3.5 snapshot workers.
  1. PIPELINE_MODULE below set to the file that holds your generate_answer(query, top_k).
  2. A judge model, ideally NOT the generator:
       JUDGE_API_KEY, JUDGE_BASE_URL (optional), JUDGE_MODEL   (any OpenAI-compatible API)
"""
import argparse
import json
import os
import random
import re
from collections import defaultdict
from pathlib import Path

from artifact_io import require_new_output, write_new_json
from rag_errors import RAGError, operational_failure

BASE = Path(__file__).resolve().parent
EVAL_SET = BASE / "data" / "eval_set.json"
CHUNKS = BASE / "data" / "chunks.json"
RESULTS = BASE / "data" / "eval_results.json"
AUDIT = BASE / "data" / "eval_audit.json"

LAW_ALIASES = {
    "Federal Decree-Law No. 33 of 2021": [r"(?<!\d)\(?33\)?\s+of\s+2021"],
    "Federal Decree-Law No. 9 of 2022": [r"(?<!\d)\(?9\)?\s+of\s+2022"],
    "Cabinet Decision No. 106 of 2022": [r"(?<!\d)\(?106\)?\s+of\s+2022", r"(?<!\d)106\s+of\s+2022"],
    "Cabinet Resolution No. 92 of 2022": [r"(?<!\d)\(?92\)?\s+of\s+2022"],
}


# ------------------------------------------------------------------ plumbing
def load_eval_set():
    with EVAL_SET.open(encoding="utf-8") as f:
        return json.load(f)["questions"]


def norm(text):
    """Whitespace-, case- and quote-insensitive form used for quote matching."""
    for a, b in (("’", "'"), ("‘", "'"), ("›", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(a, b)
    return re.sub(r"\s+", "", text).lower()


def _merge(prev, cur):
    """Append cur to prev, dropping the splitter's chunk_overlap (longest suffix of prev that starts cur)."""
    for n in range(min(len(prev), len(cur), 600), 0, -1):
        if prev.endswith(cur[:n]):
            return prev + cur[n:]
    return prev + cur


def article_texts():
    """Rebuild each article's text from its chunks, removing overlap so quotes that span chunks still match."""
    with CHUNKS.open(encoding="utf-8") as f:
        chunks = json.load(f)
    out = {}
    for c in sorted(chunks, key=lambda c: c["chunk_id"]):
        body = c["text"].split("\n", 1)[1] if "\n" in c["text"] else c["text"]
        k = (c["source_document"], c["article"])
        out[k] = _merge(out[k], norm(body)) if k in out else norm(body)
    return out


def key(item):
    return (item["source_document"], item["article"])


# ------------------------------------------------------------------ verify-set
def cmd_verify(_args):
    texts = article_texts()
    problems = 0
    for q in load_eval_set():
        for art in q["expected_articles"] + q.get("must_not_cite", []):
            if key(art) not in texts:
                problems += 1
                print(f"{q['id']}: article not in chunks.json: {key(art)}")
        for fact in q["must_include"]:
            if not fact.get("quote"):
                continue
            k = key(fact)
            if k not in texts:
                problems += 1
                print(f"{q['id']}: article missing for quote: {k}")
            elif norm(fact["quote"]) not in texts[k]:
                problems += 1
                print(f"{q['id']}: quote NOT found under {k[1]}: {fact['quote'][:80]}...")
    print("OK: all quotes verified against chunks.json" if not problems else f"\n{problems} problem(s)")
    raise SystemExit(1 if problems else 0)


# ------------------------------------------------------------------ retrieval metrics
def ranked_articles(chunks, k):
    """Top-k chunks -> unique (law, article) in rank order."""
    seen, out = set(), []
    for c in chunks[:k]:
        kk = (c["source_document"], c["article"])
        if kk not in seen:
            seen.add(kk)
            out.append(kk)
    return out


def retrieval_metrics(chunks, expected, k):
    exp = {key(a) for a in expected}
    ranked = ranked_articles(chunks, k)
    hits = [a in exp for a in ranked]
    first = next((i + 1 for i, h in enumerate(hits) if h), None)
    found = {a for a in ranked if a in exp}
    return {
        "hit": 1.0 if first else 0.0,
        "rr": 1.0 / first if first else 0.0,
        "recall": len(found) / len(exp),
        "precision": sum(hits) / len(ranked) if ranked else 0.0,
    }


def aggregate(rows):
    n = len(rows)
    return {m: sum(r[m] for r in rows) / n for m in ("hit", "rr", "recall", "precision")} if n else {}


def run_retrieval(questions, ks):
    from evaluate import retrieve_chunks  # Enforces guarded snapshot execution.
    maxk = max(ks)
    per_q, by_k = {}, {k: [] for k in ks}
    for q in questions:
        chunks = retrieve_chunks(q["question"], top_k=maxk)
        per_q[q["id"]] = {"retrieved": [(c["source_document"], c["article"]) for c in chunks]}
        if not q["expected_articles"]:
            continue
        for k in ks:
            m = retrieval_metrics(chunks, q["expected_articles"], k)
            per_q[q["id"]][f"@{k}"] = m
            by_k[k].append((q, m))
    return per_q, by_k


def print_retrieval(by_k):
    print("\nRETRIEVAL (article level; Hit=Hit Rate, MRR, Recall, Precision)")
    print(f"{'K':>3} {'Hit':>7} {'MRR':>7} {'Recall':>7} {'Prec':>7}   n")
    for k, items in by_k.items():
        if not items:
            print(f"{k:>3}   N/A (no successful retrievals to score)")
            continue
        a = aggregate([m for _, m in items])
        print(f"{k:>3} {a['hit']:7.2f} {a['rr']:7.2f} {a['recall']:7.2f} {a['precision']:7.2f}   {len(items)}")
    k = max(by_k)
    cats = defaultdict(list)
    for q, m in by_k[k]:
        cats[q["category"]].append(m)
    print(f"\nBy category @K={k}")
    for c, rows in sorted(cats.items()):
        a = aggregate(rows)
        print(f"  {c:22s} hit={a['hit']:.2f} mrr={a['rr']:.2f} recall={a['recall']:.2f} (n={len(rows)})")
    misses = [q["id"] for q, m in by_k[k] if m["hit"] == 0]
    print(f"\nMisses @K={k}: {misses or 'none'}")


# ------------------------------------------------------------------ citation check
def extract_citations(answer):
    """Return set of (law, article) the answer cites. Heuristic: nearest law mention in the same sentence,
    else the most recent law mentioned earlier. Weak signal: proves the text was WRITTEN, not that it is right."""
    cited, last_law = set(), None
    for sent in re.split(r"(?<=[.!?\n])\s+", answer):
        laws = [(m.start(), law) for law, pats in LAW_ALIASES.items() for p in pats for m in re.finditer(p, sent, re.I)]
        if laws:
            last_law = max(laws)[1]
        for m in re.finditer(r"\bArt(?:icle|\.)?\s*\(?(\d+)\)?", sent, re.I):
            if laws:
                law = min(laws, key=lambda x: abs(x[0] - m.start()))[1]
            else:
                law = last_law
            if law:
                cited.add((law, f"Article {int(m.group(1))}"))
    return cited


def citation_check(answer, q, verified_citations=None):
    # Legacy law/article text is inspectable, but never counted as verified.
    cited = {(c["source_document"], c.get("article") or "") for c in (verified_citations or [])}
    exp = {key(a) for a in q["expected_articles"]}
    bad = {key(a) for a in q.get("must_not_cite", [])}
    return {
        "verification": "evidence_ids" if verified_citations is not None else "legacy_unverified",
        "legacy_candidates": sorted(extract_citations(answer)) if verified_citations is None else [],
        "cited": sorted(cited),
        "expected_cited": sorted(cited & exp),
        "citation_recall": len(cited & exp) / len(exp) if exp else None,
        "unexpected": sorted(cited - exp),
        "wrong_law_flag": sorted(cited & bad),
    }


# ------------------------------------------------------------------ generation
# Name of the .py file (without .py) that contains your DeepSeek generate_answer(query, top_k) function.
PIPELINE_MODULE = "generate_answer"


def generate_answer(question, k, include_evidence=False, *, evidence=None, before_request=None):
    """Keep the text-only helper compatible; evaluation requests full evidence."""
    import importlib
    mod = importlib.import_module(PIPELINE_MODULE)
    kwargs = {} if evidence is None else {"evidence": evidence}
    if before_request is not None:
        kwargs["before_request"] = before_request
    result = mod.generate_answer(question, top_k=k, **kwargs)
    return result if include_evidence else result["answer"]


# ------------------------------------------------------------------ judge
from eval_judge import JUDGE_PROMPT, evaluate as evaluate_judgment


def call_judge(prompt, before_request=None):
    from openai import OpenAI
    from generate_answer import completed_answer
    with OpenAI(api_key=os.environ["JUDGE_API_KEY"], base_url=os.environ.get("JUDGE_BASE_URL"),
                timeout=30.0, max_retries=0) as client:
        if before_request is not None:
            before_request()
        resp = client.chat.completions.create(
            model=os.environ["JUDGE_MODEL"], temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
    from eval_judge import parse_response
    return parse_response(completed_answer(resp))


def judge_answer(q, answer, chunks, *, before_request=None):
    caller = call_judge if before_request is None else lambda prompt: call_judge(prompt, before_request)
    return evaluate_judgment(q, answer, chunks, caller)


# ------------------------------------------------------------------ answers command
def cmd_answers(args):
    output = require_new_output(args.output)
    from evaluate import retrieve_chunks
    questions = load_eval_set()
    if args.limit:
        questions = questions[: args.limit]
    results, ret_rows = [], {args.k: []}
    for q in questions:
        retrieval_failed = False
        try:
            chunks = retrieve_chunks(q["question"], top_k=args.k)
        except Exception as exc:
            chunks = []
            retrieval_failed = True
            generated = operational_failure(exc if isinstance(exc, RAGError) else RAGError("retrieval_unavailable", "retrieval"))
        if not retrieval_failed:
            try:
                from evidence_citations import build_evidence
                generated = generate_answer(q["question"], args.k, include_evidence=True, evidence=build_evidence(chunks))
            except Exception as exc:
                generated = operational_failure(exc if isinstance(exc, RAGError) else RAGError("internal_error", "evaluation"))
        if isinstance(generated, dict):
            answer = generated["answer"]
            validation = generated.get("citation_validation") or {"status": "legacy_unverified"}
            citations = generated.get("citations", []) if validation["status"] == "valid" else []
            citation_result = citation_check(answer, q, citations)
            citation_result["verification"] = validation["status"]
        else:
            answer = generated
            validation = {"status": "legacy_unverified"}
            citations = []
            citation_result = citation_check(answer, q)
        row = {"id": q["id"], "question": q["question"], "answer": answer,
               "retrieved": [(c["source_document"], c["article"]) for c in chunks],
               "citations": citation_result,
               "evidence_citations": citations,
               "citation_validation": validation,
               "claim_support": "not_evaluated",
               "status": generated.get("status") if isinstance(generated, dict) else None,
               "error": generated.get("error") if isinstance(generated, dict) else None}
        if q["expected_articles"] and not retrieval_failed:
            row["retrieval"] = retrieval_metrics(chunks, q["expected_articles"], args.k)
            ret_rows[args.k].append((q, row["retrieval"]))
        if not args.no_judge and row["status"] != "operational_error":
            row["judge"] = judge_answer(q, answer, chunks)
        results.append(row)
        flag = "ERROR" if row["error"] else ("PASS" if row.get("judge", {}).get("scores", {}).get("pass") else "----")
        print(f"{q['id']} {flag}  cited={len(row['citations']['cited'])}  wrong_law={row['citations']['wrong_law_flag']}")
    write_new_json(output, results)
    print_retrieval(ret_rows)
    cit = [r["citations"]["citation_recall"] for r in results if r["citations"]["citation_recall"] is not None]
    citation_score = f"{sum(cit)/len(cit):.2f}" if cit else "N/A"
    print(f"\nCITATION presence recall: {citation_score}   wrong-law flags: "
          f"{sum(bool(r['citations']['wrong_law_flag']) for r in results)}")
    print(f"Operational failures: {sum(r['status'] == 'operational_error' for r in results)}")
    judged = [r["judge"]["scores"] for r in results if r.get("judge", {}).get("status") == "valid"]
    if judged:
        print(f"ANSWER pass rate: {sum(s['pass'] for s in judged)/len(judged):.2f}   "
              f"mean fact coverage: {sum(s['fact_coverage'] for s in judged)/len(judged):.2f}   "
              f"contradictions: {sum(s['contradicted'] for s in judged)}   "
              f"traps triggered: {sum(s['forbidden_triggered'] for s in judged)}")
        print("Reminder: LLM-drafted key + LLM judge. Run `audit` and read failures before trusting these numbers.")
    print(f"Saved {output}")


def cmd_retrieval(args):
    output = require_new_output(args.output)
    per_q, by_k = run_retrieval(load_eval_set(), args.k)
    print_retrieval(by_k)
    write_new_json(output, per_q)
    print(f"Saved {output}")


# ------------------------------------------------------------------ audit
def cmd_audit(args):
    output = require_new_output(args.output)
    results = json.loads(args.input.read_text(encoding="utf-8"))
    if isinstance(results, dict):
        results = results["rows"]
    judged = [r for r in results if isinstance(r.get("judge"), dict)
              and isinstance(r["judge"].get("scores"), dict)
              and "pass" in r["judge"]["scores"]
              and r["judge"].get("status", "valid") == "valid"]
    if not judged:
        print("No judged results available to audit. No audit file written.")
        return
    qs = {q["id"]: q for q in load_eval_set()}
    sample = random.Random(args.seed).sample(judged, min(args.n, len(judged)))
    agree = total = 0
    log = []
    for r in sample:
        q = qs[r["id"]]
        answer = r.get('answer', r.get('response', {}).get('answer', ''))
        print("\n" + "=" * 78 + f"\n{r['id']}  {q['question']}\n\nANSWER:\n{answer}\n")
        for i, f in enumerate(q["must_include"]):
            v = next((f['verdict'] for f in r['judge'].get('facts', []) if f.get('id') == i), '?')
            print(f"  judge={v:12s} fact: {f['fact']}")
            if f.get("quote"):
                print(f"                 source: \"{f['quote']}\"")
        for passage in r.get('evidence', []):
            print(f"[{passage['evidence_id']}] {passage['source_document']} | {passage['article']}\n{passage['text']}")
        for claim in r['judge'].get('claims', []):
            print(json.dumps(claim, ensure_ascii=False))
        print(f"  judge overall PASS={r['judge']['scores']['pass']}")
        ans = input("Do YOU agree with the judge's overall verdict? [y/n/skip] ").strip().lower()
        if ans in ("y", "n"):
            total += 1
            agree += ans == "y"
            log.append({"id": r["id"], "judge_pass": r["judge"]["scores"]["pass"], "human_agrees": ans == "y",
                        "manual_verdict": "pass" if (r["judge"]["scores"]["pass"] == (ans == "y")) else "fail"})
    write_new_json(output, log)
    if total:
        print(f"\nJudge/human agreement: {agree}/{total} = {agree/total:.0%}. "
              "Below ~85%: tighten the judge prompt before trusting scores.")


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in {"retrieval", "answers", "report"}:
        from phase4_eval import main as controlled_main
        return controlled_main(sys.argv[1:])
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-set").set_defaults(fn=cmd_verify)
    r = sub.add_parser("retrieval"); r.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10]); r.set_defaults(fn=cmd_retrieval)
    a = sub.add_parser("answers"); a.add_argument("--k", type=int, default=10); a.add_argument("--limit", type=int)
    a.add_argument("--no-judge", action="store_true"); a.set_defaults(fn=cmd_answers)
    u = sub.add_parser("audit"); u.add_argument("--n", type=int, default=25); u.add_argument("--seed", type=int, default=0); u.set_defaults(fn=cmd_audit)
    r.add_argument("--output", type=Path, default=BASE / "data" / "eval_retrieval.json")
    a.add_argument("--output", type=Path, default=RESULTS)
    u.add_argument("--input", type=Path, default=RESULTS, help="Answer results to audit")
    u.add_argument("--output", type=Path, default=AUDIT)
    args = p.parse_args()
    if args.cmd == "audit" and args.n < 1:
        p.error("--n must be positive")
    try:
        args.fn(args)
    except FileExistsError as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
