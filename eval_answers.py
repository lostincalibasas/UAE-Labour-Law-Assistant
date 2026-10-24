"""RAG evaluation: retrieval metrics + citation check + LLM-judged answer correctness.

Commands (run from the compliance-rag project root, next to data/chunks.json):

  python eval_answers.py verify-set                 # check every quote exists in chunks.json under its article
  python eval_answers.py retrieval --k 1 3 5 10     # retrieval metrics only (no LLM calls)
  python eval_answers.py answers --k 10             # retrieval + generation + citation + judge
  python eval_answers.py audit --n 25               # hand-check judge verdicts, get agreement rate

Needs for `answers`:
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
    from retrieve_bge import retrieve_chunks  # your existing retriever
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


def citation_check(answer, q):
    cited = extract_citations(answer)
    exp = {key(a) for a in q["expected_articles"]}
    bad = {key(a) for a in q.get("must_not_cite", [])}
    return {
        "cited": sorted(cited),
        "expected_cited": sorted(cited & exp),
        "citation_recall": len(cited & exp) / len(exp) if exp else None,
        "unexpected": sorted(cited - exp),
        "wrong_law_flag": sorted(cited & bad),
    }


# ------------------------------------------------------------------ generation
# Name of the .py file (without .py) that contains your DeepSeek generate_answer(query, top_k) function.
PIPELINE_MODULE = "generate_answer"


def generate_answer(question, k):
    """Calls YOUR pipeline function: generate_answer(query, top_k) -> {"answer": str, "sources": [...]}."""
    import importlib
    mod = importlib.import_module(PIPELINE_MODULE)
    return mod.generate_answer(question, top_k=k)["answer"]


# ------------------------------------------------------------------ judge
JUDGE_PROMPT = """You are grading an answer from a legal RAG assistant. Be strict and literal.

QUESTION:
{question}

ANSWER UNDER TEST:
{answer}

REQUIRED FACTS (each backed by a source quote; judge the ANSWER against the fact, using the quote only as reference):
{facts}

FORBIDDEN CLAIMS (an item is "triggered" only if the answer asserts it as the answer):
{avoid}

RETRIEVED CONTEXT GIVEN TO THE ANSWERER:
{context}

For every required fact return one verdict:
  "present"      - answer states it correctly (numbers, conditions, who/when must match)
  "missing"      - not stated
  "contradicted" - stated with a different number/condition/applicability
Also list "unsupported_claims": specific legal claims in the answer that are NOT supported by the retrieved context.
Return ONLY JSON:
{{"facts":[{{"id":0,"verdict":"present|missing|contradicted","evidence":"short"}}],
 "forbidden":[{{"id":0,"triggered":false,"evidence":"short"}}],
 "unsupported_claims":["..."]}}"""


def call_judge(prompt):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["JUDGE_API_KEY"], base_url=os.environ.get("JUDGE_BASE_URL"))
    resp = client.chat.completions.create(
        model=os.environ["JUDGE_MODEL"], temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def judge_answer(q, answer, chunks):
    facts = "\n".join(
        f"[{i}] {f['fact']}" + (f"\n    source ({f['article']}): \"{f['quote']}\"" if f.get("quote") else "")
        for i, f in enumerate(q["must_include"]))
    avoid = "\n".join(f"[{i}] {a}" for i, a in enumerate(q["must_not_include"])) or "(none)"
    context = "\n---\n".join(c["text"][:1500] for c in chunks) or "(none)"
    res = call_judge(JUDGE_PROMPT.format(question=q["question"], answer=answer, facts=facts, avoid=avoid, context=context))
    verdicts = [f["verdict"] for f in res.get("facts", [])]
    n = len(q["must_include"])
    present = sum(v == "present" for v in verdicts)
    contradicted = sum(v == "contradicted" for v in verdicts)
    triggered = sum(bool(t.get("triggered")) for t in res.get("forbidden", []))
    res["scores"] = {
        "fact_coverage": present / n if n else None,
        "contradicted": contradicted,
        "forbidden_triggered": triggered,
        "unsupported_claims": len(res.get("unsupported_claims", [])),
        "pass": present == n and contradicted == 0 and triggered == 0,
    }
    return res


# ------------------------------------------------------------------ answers command
def cmd_answers(args):
    from retrieve_bge import retrieve_chunks
    questions = load_eval_set()
    if args.limit:
        questions = questions[: args.limit]
    results, ret_rows = [], {args.k: []}
    for q in questions:
        chunks = retrieve_chunks(q["question"], top_k=args.k)
        answer = generate_answer(q["question"], args.k)
        row = {"id": q["id"], "question": q["question"], "answer": answer,
               "retrieved": [(c["source_document"], c["article"]) for c in chunks],
               "citations": citation_check(answer, q)}
        if q["expected_articles"]:
            row["retrieval"] = retrieval_metrics(chunks, q["expected_articles"], args.k)
            ret_rows[args.k].append((q, row["retrieval"]))
        if not args.no_judge:
            row["judge"] = judge_answer(q, answer, chunks)
        results.append(row)
        flag = "PASS" if row.get("judge", {}).get("scores", {}).get("pass") else "----"
        print(f"{q['id']} {flag}  cited={len(row['citations']['cited'])}  wrong_law={row['citations']['wrong_law_flag']}")
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print_retrieval(ret_rows)
    cit = [r["citations"]["citation_recall"] for r in results if r["citations"]["citation_recall"] is not None]
    print(f"\nCITATION presence recall: {sum(cit)/len(cit):.2f}   wrong-law flags: "
          f"{sum(bool(r['citations']['wrong_law_flag']) for r in results)}")
    judged = [r["judge"]["scores"] for r in results if "judge" in r]
    if judged:
        print(f"ANSWER pass rate: {sum(s['pass'] for s in judged)/len(judged):.2f}   "
              f"mean fact coverage: {sum(s['fact_coverage'] for s in judged)/len(judged):.2f}   "
              f"contradictions: {sum(s['contradicted'] for s in judged)}   "
              f"traps triggered: {sum(s['forbidden_triggered'] for s in judged)}")
        print("Reminder: LLM-drafted key + LLM judge. Run `audit` and read failures before trusting these numbers.")
    print(f"Saved {RESULTS}")


def cmd_retrieval(args):
    per_q, by_k = run_retrieval(load_eval_set(), args.k)
    print_retrieval(by_k)
    (BASE / "data" / "eval_retrieval.json").write_text(json.dumps(per_q, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ audit
def cmd_audit(args):
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    qs = {q["id"]: q for q in load_eval_set()}
    sample = random.Random(args.seed).sample([r for r in results if "judge" in r], min(args.n, len(results)))
    agree = total = 0
    log = []
    for r in sample:
        q = qs[r["id"]]
        print("\n" + "=" * 78 + f"\n{r['id']}  {q['question']}\n\nANSWER:\n{r['answer']}\n")
        for i, f in enumerate(q["must_include"]):
            v = r["judge"]["facts"][i]["verdict"] if i < len(r["judge"].get("facts", [])) else "?"
            print(f"  judge={v:12s} fact: {f['fact']}")
            if f.get("quote"):
                print(f"                 source: \"{f['quote']}\"")
        print(f"  judge overall PASS={r['judge']['scores']['pass']}")
        ans = input("Do YOU agree with the judge's overall verdict? [y/n/skip] ").strip().lower()
        if ans in ("y", "n"):
            total += 1
            agree += ans == "y"
            log.append({"id": r["id"], "judge_pass": r["judge"]["scores"]["pass"], "human_agrees": ans == "y"})
    AUDIT.write_text(json.dumps(log, indent=2), encoding="utf-8")
    if total:
        print(f"\nJudge/human agreement: {agree}/{total} = {agree/total:.0%}. "
              "Below ~85%: tighten the judge prompt before trusting scores.")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-set").set_defaults(fn=cmd_verify)
    r = sub.add_parser("retrieval"); r.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10]); r.set_defaults(fn=cmd_retrieval)
    a = sub.add_parser("answers"); a.add_argument("--k", type=int, default=10); a.add_argument("--limit", type=int)
    a.add_argument("--no-judge", action="store_true"); a.set_defaults(fn=cmd_answers)
    u = sub.add_parser("audit"); u.add_argument("--n", type=int, default=25); u.add_argument("--seed", type=int, default=0); u.set_defaults(fn=cmd_audit)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
