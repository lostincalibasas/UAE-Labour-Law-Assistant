# Phase 4 offline evaluation

Questions: 74

| K | Scored | Hit | MRR | Recall | Precision |
|---|---|---|---|---|---|
| 1 | 72 | 0.7639 | 0.7639 | 0.6875 | 0.7639 |
| 3 | 72 | 0.8611 | 0.8102 | 0.8125 | 0.4282 |
| 5 | 72 | 0.9167 | 0.8252 | 0.8819 | 0.2741 |
| 10 | 72 | 0.9444 | 0.8303 | 0.9306 | 0.1535 |

## Answer metrics

| Metric | Numerator / denominator | Value |
|---|---|---|
| answer_correctness | 0 / 0 | Not evaluated |
| strict_answer_pass | 0 / 0 | Not evaluated |
| key_fact_coverage_micro | 0 / 0 | Not evaluated |
| claim_faithfulness | 0 / 0 | Not evaluated |
| citation_semantic_precision | 0 / 0 | Not evaluated |
| citation_claim_coverage | 0 / 0 | Not evaluated |
| citation_identity_acceptance | 0 / 0 | Not evaluated |
| wrong_law_claim_rate | 0 / 0 | Not evaluated |
| contradicted_claim_rate | 0 / 0 | Not evaluated |
| out_of_scope_abstention | 0 / 0 | Not evaluated |
| unnecessary_abstention | 0 / 0 | Not evaluated |
| forbidden_source_citation_rate | 0 / 0 | Not evaluated |
| judge_failure_rate | 0 / 0 | Not evaluated |

## Outcomes

- not_generated: 74

## Manual review candidates

- Q027: expected_article_missing_at_10
- Q041: human_answer_key_review_required; expected facts unchanged; expected_article_missing_at_10
- Q068: human_answer_key_review_required; expected facts unchanged; expected_article_missing_at_10
- Q072: expected_article_missing_at_10

## Definitions

- retrieval: Top-k chunks, deduplicated (document, article); RR uses unique-article rank. Only cases with expected articles and successful retrieval enter denominators.
- answer_correctness: Judge answer_correct / schema-valid judgments; invalid/missing judgments excluded and reported separately.
- key_fact_coverage_micro: Present rubric facts / all required facts in schema-valid judgments.
- claim_faithfulness: Supported extracted claims / all extracted claims in valid judgments; uncited claims count as unsupported.
- citation_identity_acceptance: Responses accepted by deterministic ID validation / non-operational generated responses, including abstentions. Not semantic accuracy.
- citation_semantic_precision: Supported, correctly attributed cited claims / cited claims assessed by a valid judge.
- abstention: Two fully unanswerable items measured separately; partial items remain answerable. Citation rejection and operational failure are never legitimate abstention.
- unnecessary_abstention: Abstentions with judge evidence_sufficient=true / all schema-valid judged answerable items.
- forbidden_source_citation_rate: Responses citing a dataset must_not_cite document/article / non-operational responses with citation checks. A dataset flag, not a semantic wrong-law finding.
- causality: Expected-article misses are retrieval signals, not proof of insufficient evidence. Failure attribution uses judge evidence_sufficient when available.

## Limitations

- All answer keys remain unreviewed LLM drafts; Q041 and Q068 need scope review.
- Judge semantics and claim enumeration require manual calibration; deterministic schema checks cannot prove correctness or complete claim extraction.
- Zero denominators mean not evaluated, never zero accuracy. No live answer quality conclusions from retrieval-only runs.

## Execution and artifact protection

- Final run: `runs/phase4-offline-final-01.json`; machine report: `runs/phase4-report-01.json`.
- 74 real BGE retrieval queries per run; generation requests **0**, judge requests **0**. An initial offline verification run was also retained; both runs produced identical captured-evidence hashes for all 74 questions.
- Final retrieval time summed across 74 questions: **21.284 seconds**, including **14.925 seconds** for the first query/model initialization. No generation or judging latency is available.
- Complete index copied under Windows write-denying locks to `C:/Users/Admin/AppData/Local/Temp/compliance-rag-eval-d44rykt8/working`. Every recorded Chroma opening used that copy.
- Three collections were logically unchanged before/after and after reopen. Stored BGE text/source/article records matched the exported 252 chunks.
- **All 36 protected artifacts unchanged**, with before/after hashes saved in `runs/phase4-artifact-integrity-01.json`. No datasets, original indexes, or prior evaluation outputs were overwritten. All new outputs and temporary copies are retained.
- **103 tests passed, 0 failed** (80 prior tests plus 23 Phase 4 tests). Prior mocks were adapted to guarded retrieval and the strict judge schema; test intentions remain intact. Corpus checks, dataset quote verification and `git diff --check` passed.

## Four retrieval misses

| ID | Expected document / article | First chunk rank | Supporting stored chunk | Finding |
|---|---|---:|---|---|
| Q027 | Federal Decree-Law 33/2021, Article 6 | 17 | 61 | Domestic-worker recruitment provisions in Cabinet Decision 106 dominate the top ranks; the expected private-sector passage is below K=10. Another Article 6 chunk ranks 37. |
| Q041 | Federal Decree-Law 33/2021, Article 3 | 106 | 56 | Top results concern domestic-worker rules, while the general law's scope exclusion ranks much lower. |
| Q068 | Federal Decree-Law 9/2022, Article 26 | 14 | 240 | Contract termination and entitlement passages outrank the expected limitation provision. |
| Q072 | Federal Decree-Law 33/2021, Article 27 | 12 | 98 | Domestic-worker wages, wage definitions and payment provisions outrank the expected minimum-wage provision. |

All quoted facts for these four questions exist wholly inside single stored chunks; reconstructed-article checks also passed. These observations do not support missing-corpus or chunk-boundary explanations for the four misses. Ranking competition and employment-regime ambiguity are plausible explanations, not proven causes.

Each diagnostic used one query requesting up to all 252 passages; generation evidence remains the first ten. Query depth can affect approximate nearest-neighbor rankings. In this run, **top-ten document/article ordering matched the existing saved retrieval output for all 74 questions**, and aggregate metrics matched the prior baseline. No retrieval algorithm, query prefix, embeddings, or production K changed.

## Manual review examples

- **Q041:** review whether required government/armed-forces exclusions overconstrain a question specifically about domestic-worker applicability. Both expected facts are retained unchanged.
- **Q068:** review whether the required court-fee exemption is necessary for a question asking about the time limit for suing. Both expected facts are retained unchanged.
- **Q027:** check whether a generated answer substitutes a domestic-worker recruitment rule for the private-sector rule, even when it cites a valid evidence ID.
- **Q072:** distinguish a qualified answer about what the corpus establishes from an invented numeric minimum wage or an unnecessary blanket fallback. This remains an answerable partial case, not one of the two fully out-of-scope items.

No generated answers exist from these offline runs, so these are targeted review scenarios, not observed generation failures. The saved rows contain exact evidence/excerpts and deeper rankings for inspection. Automated judgments and subsequent manual verdicts are separate artifacts.

## Proposed ten-question pilot ? not executed

`Q001, Q010, Q027, Q041, Q044, Q049, Q068, Q072, Q073, Q074`

This covers probation/notice, notice-period equality, all four retrieval misses, domestic-worker sick leave, passport attribution, and both fully out-of-scope questions. Use production top-10 retrieval, without diagnostic depth, for this pilot.

- Maximum **10 DeepSeek generation requests + 10 judge requests**; fewer judge calls if generation fails or citations are rejected.
- Dry-run manifest: `runs/phase4-pilot-plan-01.json`. Actual requests: **0**; no index opened by the dry run.
- Generation and judge budgets are independent, SDK retries are disabled, and outputs require new paths. A token/currency estimate requires the chosen judge model and observed response lengths; no pricing assumptions were made.
- Obtain separate approval for live requests and select/configure the judge. Manually review all ten cases and the two flagged answer keys before interpreting scores or authorizing the remaining dataset.

## Implementation and compatibility

Added `phase4_eval.py`, `eval_judge.py`, `eval_report.py`, and `tests/test_phase4.py`.
Updated `eval_answers.py`, `generate_answer.py`, `evaluate.py`, `index_isolation.py`, `README.md`, and test fixtures in `tests/test_phase1.py`, `tests/test_phase2.py`, `tests/test_phase3.py`.

The expanded retrieval/answers CLI now requires explicit IDs and output paths; `--limit` is replaced by IDs. Defaults make no API requests. Output is a versioned run object, while audit supports old and new formats. Legacy direct evaluation retrieval is refused outside guarded workers. The application API remains compatible, with optional keyword-only captured evidence and request hooks. Production responses retain `claim_support: not_evaluated`; automated semantic grades are stored separately.

No hybrid search, reranking, caching, deployment changes, index repair, or live API testing was introduced. Remaining limits: unreviewed corpus-specific keys, judge bias/incomplete claim extraction, unavailable live quality metrics, provider nondeterminism, Windows-only snapshot locking, private Chroma guard API, and retained temporary disk usage. Fingerprints aid reproducibility but cannot guarantee identical future provider responses.
