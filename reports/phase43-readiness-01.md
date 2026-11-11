# Phase 4.3 production-readiness assessment

**Status: awaiting independent human review. Production is not approved.** Independent validation has not run or passed. Actual human judgments received: **0**. No paid APIs, generation, reranking, hybrid search, index rebuild or production change occurred.

## Deliverables

- **Blinded delivery packet:** `review/phase43/worksheet.md` and `worksheet.json`, with reviewer instructions, all three source PDFs and the complete unranked corpus export. There are 32 shuffled Vnnn questions and no populated judgment fields. No predictions, per-question expected law labels, prior keys, selected excerpts or baseline ranking results are included.
- **Private administrator manifest:** `runs/phase43-private-manifest-01.json`. It holds construction coverage, frozen selector/retriever/corpus fingerprints and prospective criteria. Do not send it or historic evaluation material to the reviewer.
- **Offline import tooling:** `independent_review.py` validates completed human submissions and preserves judgments separately. Blank, edited, dropped, duplicate, incomplete or unattested reviews fail before any index access.
- **Offline comparison tooling:** `independent_eval.py` uses the existing guarded, write-locked snapshot workflow. Only completed reviewer-attested imports can reach it. Runtime routing receives question text and source metadata; human answers enter scoring afterward.
- **Administrator procedure/checklist:** [validation procedure](phase43-validation-procedure-01.md).
- **Separate historical-key adjudication:** [Q041/Q068 review sheet](phase43-key-review-01.md), with separate pending human fields in `runs/phase43-key-review-01.json`. Keep this outside the primary blinded packet until that submission is locked.

The packet questions are assistant-authored prompts, not independent human judgments or fully independent question design. The reviewer must supply the actual legal labels and at least ten independently authored Hnnn questions. These facts are explicit in the packet. No reviewer was contacted and no materials were sent externally.

## Overfitting and design review

Phase 4.2 does not use ground-truth labels at runtime: its inputs are question text and available source names. That is necessary but does not establish generalization. The hand-written rules, confidence/fallback triggers and local challenge cases were developed with knowledge of the same project and known retrieval misses. Forty matches on forty locally authored routing expectations are not an independent test.

Specific risks remain:

- The selector recognizes a small English vocabulary and finite regular-expression windows. Indirect wording, long-distance negation, single-quoted context, colloquial roles or unfamiliar jurisdiction names may evade the safeguards or trigger unnecessary fallback.
- Employment context may matter more than occupational words. A cleaner, driver, agency employee or office worker cannot always be legally classified from the wording alone.
- The metadata catalog contains four named documents. Unknown sources disable filtering, which is conservative but can remove the expected benefit. Known titles/years do not prove the corpus is current, authoritative, complete or applicable.
- Mixed questions can retain both regimes safely yet still miss needed scope provisions. Q041 and Q068 were not solved by metadata filtering; their key-relevance concerns remain open.
- Source and article identity are proxies. Correct source filtering can still return a chunk lacking the necessary claim, conditions or exceptions. A higher Hit@10 alone cannot establish answer quality.
- The previous sample is small, and timing varies with machine load. Zero observed exclusions is not proof that harmful exclusions cannot occur.

The selector is frozen for this round. Changes to selector, retriever or corpus invalidate the import fingerprint checks and require a new round. The rules are not tuned against reviewer labels by this tooling.

## What the future comparison measures

Once a real complete human submission is supplied, the evaluator compares original BGE Top-10 with frozen experimental Top-10 using the same query embedding. It records Hit/recall/MRR/precision, ranked evidence, changes at K=1/3/5/10, timing, human/system selection agreement, incorrect forced filters, conservative no-filter cases and two exclusion checks:

1. A filter excludes a source the reviewer marked necessary, even if baseline Top-10 already missed it.
2. A necessary in-corpus article present in baseline Top-10 is lost from experimental Top-10.

Either exclusion is a blocking concern. Aggregate gains cannot cancel one demonstrated harmful exclusion. Outside-corpus and uncertain evidence are not silently thrown away. Invalid in-corpus references or a mismatch between indexed text and the reviewed export stop the run for corpus/key review rather than scoring misleading results.

Human judgments and automatic selections remain distinct fields; reviewer decisions are neither generated nor repaired by the evaluator. Human identity, expertise and independence are attested by the submitter, not authenticated by software. The administrator must verify them.

No answer-correctness, faithfulness or response-abstention scores are produced by this phase: there are no generation or judge calls. Legally unanswerable/out-of-scope cases are still useful for judging whether a forced source filter is safe.

## Preregistered readiness checklist

| Requirement | Current state |
|---|---|
| Frozen candidate, original retriever and corpus fingerprints | Prepared and verified |
| Blinded packet with no machine judgments | Prepared; all human fields blank |
| Qualified reviewer independent of development and prior outputs | Pending human verification |
| At least 42 complete reviews: all 32 prepared cases plus at least 10 reviewer-authored questions | 0 received |
| At least 4 cases in each of 6 human-assigned coverage domains | Pending |
| At least 4 general-filter, 4 domestic-filter and 8 no-filter human judgments | Pending |
| At least 24 article-scoreable cases, 20 with necessary in-corpus evidence, and 10 actual filter activations | Pending |
| No low-confidence or uncertain-availability judgments without adjudication | Pending |
| Zero harmful necessary-evidence exclusions and zero incorrect forced filters | Not measured independently |
| No per-case Hit/recall/MRR regressions at K=1/3/5/10; aggregate Hit@10 and recall noninferior to baseline | Not measured independently |
| Median latency at most baseline ?1.25 +5 ms; p95 at most baseline ?1.50 +5 ms | Not measured independently |
| Safe snapshot execution and protected-artifact integrity | Tooling tested; human evaluation not run |
| Separate Q041/Q068 review and manual passage-support inspection | Pending |
| Explicit production approval | Not granted |

These are prospective engineering acceptance gates, not legal standards or validated risk thresholds. If cases do not cover a domain, collect more independent questions; do not change legal labels to meet quotas. If a threshold is changed after seeing results, record a new validation round rather than silently accepting the old test.

Passing every automated gate only yields `awaiting_manual_signoff`; the software never approves, deploys or promotes production changes. The separate answer-key review, source support checks and explicit approval remain necessary. An independently reviewed end-to-end answer-quality trial may still be warranted after separate approval; it is not run here.

## Separate outstanding legal-key review

**Q041:** whether government/armed-forces/police exclusions should be mandatory facts for a question specifically about domestic-worker applicability. **Q068:** whether judicial-fee exemption should be mandatory for a question specifically about the filing time limit. These are possible overconstraint concerns, not established legal errors. All original facts and outcomes remain unchanged. Original invalid-judge reviews Q044/Q049/Q073 also remain unresolved.

Do not expose those labeled historical requirements to the primary independent reviewer before their submission is frozen. Use a separate adjudicator or review them after the blind phase.

## Regression tests and protection

- **164 regression tests passed; 0 failed.** New tests cover packet blinding, private-manifest separation, blank/incomplete review refusal, attestations, provenance, edited/dropped cases, frozen inputs, strict JSON, non-overwriting files, human/automatic separation, harmful exclusion despite a positive Hit@10, ranking losses, latency gates, no-filter identity and index-access refusal before valid human data.
- The actual blank packet was submitted to the importer as a negative check and correctly rejected; **no human-import artifact was created**.
- Tests use temporary synthetic fixtures explicitly marked as not human review. They are software tests, not independent validation results.
- Dataset quote checks and `git diff --check` passed.
- **All 36 protected artifacts, all previous run/report outputs, production code and the frozen selector remain unchanged.** `runs/phase43-integrity-01.json` records verification. The reviewer PDF/text copies match source hashes.
- No real Chroma client or live model/API was opened for this phase. Future human-data evaluation is limited to a verified isolated copy; the original index is never a client target.

Added `review_seed_questions.py`, `independent_review.py`, `independent_eval.py`, `tests/test_phase43.py`, the reviewer packet and new administrator artifacts. Updated README documentation. No new dependencies, infrastructure or production imports were introduced.

**Recommendation:** keep the selector experimental. Arrange actual blinded human review and collect the independent questions before making any claim that independent validation has passed.
