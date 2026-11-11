# Phase 4.3 validation procedure ? administrator only

Do not send this document, private manifests, selector source, historic keys or result reports to the blinded reviewer. Deliver only review/phase43/ with its complete neutral corpus. Nothing has been sent externally by the assistant.

## 1. Arrange an actual independent human reviewer

Use a reviewer with relevant UAE employment-law expertise who has not developed the selector and has not seen its predictions, historical keys or rankings. Software records attestations but cannot authenticate independence or qualifications. Prepared questions are assistant-authored prompts, not independent legal judgments.

The packet contains 32 shuffled Vnnn questions and blank human fields. The reviewer must also independently author at least ten Hnnn questions and judge them. If evidence coverage is insufficient, collect more independent cases; never ask the reviewer to change legal judgments to satisfy coverage quotas.

Have the reviewer use the full PDFs, not selected snippets. Record source versions, missing corpus evidence and any additional authoritative sources. The files are translations/corpus material, not a guarantee of current authoritative law. The original source PDFs and frozen chunk export are unchanged.

## 2. Complete and lock the blinded submission

The reviewer writes a new completed-review.json, leaving worksheet.json intact. All prepared IDs/questions must remain unchanged. Each case requires legislation, supporting articles with necessary/optional and corpus-availability annotations, answerability, permitted filtering, confidence, explanation, source basis and reviewer-assigned coverage tags.

Null means unfinished. A legitimate empty list must be explained. A fully reviewed case may legitimately need clarification; its permitted_filter must be no_filter. Unknown availability and low confidence remain explicit and block readiness until adjudicated. Do not manufacture references to make a case scoreable.

Freeze the full submission before any routing or ranking results are disclosed. Keep a new, versioned copy for each adjudicated submission. Do not fill it with an LLM or treat assistant-authored labels as independent human judgments.

## 3. Import without opening any index

```powershell
python -B independent_review.py import --input review/phase43/completed-review.json --manifest runs/phase43-private-manifest-01.json --output runs/phase43-human-import-NEW.json
```

The importer requires explicit true human/blinding attestations, complete case judgments, distinct article IDs and evidence rationales. It rejects edited/dropped prepared questions, duplicate IDs, inconsistent provenance, malformed JSON and unknown fields in case judgments. It preserves human judgments exactly; no canonicalization, label repair or inferred human verdict is performed.

It also verifies frozen selector, BGE retriever and corpus hashes, and the preregistered criteria. Changed code/corpus requires a new validation round; do not reuse an exposed test set to tune and claim independent validation. An imported dataset is not a passing evaluation and does not prove the attestations are true.

The current blank worksheet was tested and correctly rejected; there is no real human-import artifact yet.

## 4. Run the offline isolated comparison only after submission

Close index users so Phase 3.5 write-denying snapshot locks can be acquired.

```powershell
python -B independent_eval.py --input runs/phase43-human-import-NEW.json --output runs/phase43-independent-results-NEW.json
```

The completed human import is validated before any index access. The runner copies the complete locked original index into a new temporary workspace, verifies byte equality, and launches a fresh worker with the shared Chroma path guard. Every native client is restricted to the working copy. It verifies that stored text/source/article records match the reviewed chunk export and that all human in_corpus references exist; otherwise it stops for corpus/key review instead of scoring phantom articles.

Baseline and experimental searches use the same cached BGE query embedding and Top-10 settings. Only question text and available source names enter the selector. Human labels enter scoring after retrieval. Unfiltered cases reuse the exact baseline result; there is no reranking, hybrid retrieval or API call. Timing separates encoding, selection and queries, with model initialization reported separately.

Output contains the imported human judgments, separately identified automatic selections, exact captured evidence, article-level Hit/recall/MRR, per-case ranking regressions, incorrect forced filters, conservative no-filter cases, necessary-source exclusions and observed necessary-article losses. The tool checks all collection logical contents before/after and after reopen, plus original index hashes. All destinations use exclusive writes; choose new paths for every run.

## 5. Interpret harmful exclusions conservatively

Two checks are distinct:

- Structural exclusion: a source containing reviewer-marked necessary evidence is excluded by the selected source filter, even if baseline Top-10 happened to miss that article too. Outside-corpus necessary sources are reported rather than silently discarded.
- Observed loss: a reviewer-marked necessary in-corpus article was in baseline Top-10 but disappeared from experimental Top-10.

Either blocks readiness. Hit@10 can remain positive while another necessary article is lost; do not use aggregate improvement to excuse such a case. Correct filtering is agreement with a human judgment, not automatic proof that a legal answer is correct. Article identity is only a proxy: inspect the captured passages for actual claim support.

Answerability/empty-reference cases remain in regime-selection denominators but not article-retrieval denominators. No answer correctness, faithfulness or response-abstention metrics are asserted, because this phase does not generate answers.

## 6. Apply the preregistered promotion checklist

The private manifest freezes these proposed engineering acceptance gates before human judgments:

- At least 42 reviewed cases, including all 32 prepared cases and at least ten independently reviewer-authored questions.
- At least four reviewer-tagged cases in each of six coverage domains; at least four human general-filter cases, four domestic-filter cases and eight no-filter cases.
- At least 24 article-scoreable cases, 20 cases with necessary in-corpus evidence, and ten actual filter activations. This prevents empty or never-filtering sets from passing vacuously.
- No incomplete reviews, low-confidence labels, or uncertain corpus availability; authenticate expertise/independence and adjudicate unresolved labels without silently editing history.
- **Zero demonstrated harmful exclusions of necessary legal evidence and zero incorrect forced filters.**
- No per-case Hit, recall or reciprocal-rank regressions at K=1/3/5/10; aggregate Hit@10 and recall must not fall below baseline.
- Median latency no greater than baseline ?1.25 +5 ms; p95 no greater than baseline ?1.50 +5 ms. These are prospective engineering thresholds, not validated legal standards. Investigate timing noise before interpreting a failure; do not silently change thresholds after results.
- Frozen selector, retriever and corpus; safe isolated execution; unchanged protected artifacts.
- Separate Q041/Q068 answer-key review, manual inspection of necessary evidence, and explicit production approval remain mandatory.

Passing automatic gates yields awaiting_manual_signoff, never production approval or deployment. A small independent set with no observed harm does not prove universal safety. Any change after unblinding requires new independent validation. No production change or paid end-to-end test is executed by these scripts.

## 7. Separate historical-key adjudication

Only after locking the primary submission, or with a different adjudicator, use reports/phase43-key-review-01.md and runs/phase43-key-review-01.json. Q041's government/armed-forces exclusions and Q068's judicial-fee fact remain unresolved relevance concerns. Record rationale and proposed changes separately; the existing evaluation dataset remains unchanged.

## Current state

Reviewer judgments received: **0**. Independent retrieval evaluation: **not run**. Production readiness: **pending independent human review, not approved**. Regression tests exercise synthetic protocol fixtures only; they are not human validation results.
