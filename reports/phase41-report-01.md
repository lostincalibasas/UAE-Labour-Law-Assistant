# Phase 4.1 ? evaluation reliability and retrieval diagnostics

Completed offline. **Zero paid/API requests.** No production retrieval/generation changes, embedding rebuilds, answer-key edits or historical judgment repairs.

## Judge failure diagnosis

Q044, Q049 and Q073 remain evaluation failures. Inspection of both the saved pilot and retained temporary checkpoints confirmed that only `judge_schema_invalid` was stored. **Their exact schema violations and generating causes cannot be recovered from the retained artifacts.** No raw response was fabricated or re-requested.

The confirmed diagnostic defect was loss of the failing field and original response: JSON parsing and schema errors were collapsed into one generic code. Markdown-wrapped JSON, omitted IDs, altered quote spans, mismatched citation mappings and wrong field types are possible violations covered by tests, not established explanations for these three cases.

Implemented evaluation-only fixes:

- Concrete JSON example and per-question fact/forbidden/evidence-ID contract; exact claim-quote instructions.
- Explicit distinction between correct safe abstention and required-fact coverage. Inconsistent abstention booleans are rejected, not repaired.
- Strict parsing rejects wrappers, duplicate JSON keys and non-finite numbers. Structural validation reports precise safe paths/codes (for example `$.claims[0].quote: quote_not_exact_answer_span`), including multiple violations where parsing permits.
- Failure records include validator version 2 and response byte count/hash where available. Arbitrary response text, unexpected key names, credentials and provider exception bodies are not logged.
- Malformed/incomplete judgments never pass. Valid citation identity remains separate from semantic support.

The revised prompt has **not** been tested through a paid judge call. Strict schema acceptance does not establish legal correctness or guarantee complete claim extraction.

## Manual review

[Worksheet](phase41-manual-review-01.md) covers Q044/Q049/Q073 plus Q041/Q068. Its companion `runs/phase41-manual-review-01.json` contains exact captured excerpts, immutable copies of original automated outcomes and separate null human-verdict fields.

- Q041: assess whether government/armed-forces exclusions overconstrain a question focused on domestic-worker applicability.
- Q068: assess whether the judicial-fee exemption belongs in a question focused on the filing time limit.
- Q044/Q049: manually assess facts and claim support; a valid evidence ID does not substitute for the rejected judge result.
- Q073: review its observed fallback separately from its invalid judge response.

No human verdict has been supplied and no expected fact has been changed.

## Retrieval method and metrics

All 74 existing questions were exercised in a fresh, byte-verified isolated index copy. The 72 questions with expected articles enter retrieval denominators; two out-of-scope questions have no expected-article score. Query embeddings were computed once per question and reused for all offline variants. No stored document embeddings were rebuilt.

Dense searches requested 10, 20 and 50 candidates. Explicit question wording determines regime: main/general labour law or private sector selects Law 33/2021; domestic/household wording selects Law 9/2022, Decision 106/2022 and Resolution 92/2022. Unspecified wording does not filter. This classification was checked against corpus text, including Resolution 92 provisions on domestic-worker recruitment offices.

Lexical reranking uses corpus-derived BM25 and fixed equal-weight reciprocal-rank fusion (constant 60). It only reorders existing dense candidates. No question IDs, expected articles, required facts or evaluation categories choose retrieval behavior. The initial parameters were fixed before scoring. The scoped replay is a disclosed adaptive follow-up after the Q004 regression, not held-out validation.

Hit is presence of any expected document/article; recall is the mean fraction of expected document/articles found per question. MRR uses deduplicated article rank, preserving the baseline definition. Cutoffs below count chunks, not unique articles. Larger-pool rows score their entire displayed cutoff; reranked rows still serve ten passages.

| Variant | Scored cutoff | Hit | Expected-article recall | MRR | Median query/rerank ms | Median total ms* |
|---|---:|---:|---:|---:|---:|---:|
| baseline10 | 10 | 68/72 (94.44%) | 93.06% | 0.8303 | 2.79 | 92.57 |
| pool20 | 20 | 71/72 (98.61%) | 97.92% | 0.8341 | 3.11 | 93.21 |
| pool50 | 50 | 71/72 (98.61%) | 98.61% | 0.8341 | 4.08 | 94.03 |
| postfilter20_top10 | 10 | 70/72 (97.22%) | 95.83% | 0.8641 | 3.12 | 93.22 |
| prefilter10 | 10 | 70/72 (97.22%) | 95.83% | 0.8641 | 3.16 | 93.39 |
| rrf20_top10 | 10 | 70/72 (97.22%) | 96.53% | 0.7784 | 3.43 | 93.55 |
| rrf50_top10 | 10 | 69/72 (95.83%) | 95.83% | 0.7837 | 4.79 | 94.65 |
| prefilter50 | 20 | 72/72 (100.00%) | 99.31% | 0.8669 | 4.76 | 94.94 |
| prefilter50 | 50 | 72/72 (100.00%) | 100.00% | 0.8669 | 4.76 | 94.94 |
| prefilter_rrf50_top10 | 10 | 71/72 (98.61%) | 98.61% | 0.8238 | 5.65 | 95.57 |
| scoped_prefilter_rrf50_top10 | 10 | 72/72 (100.00%) | 100.00% | 0.8590 | 4.58 | 93.76 |

*Total includes query encoding, excludes initial model load (19.84 seconds). Query-depth order rotated across questions. These are single-run, warm-cache timings, not statistically significant performance claims. The scoped replay reuses measured branch timings; it is not a fresh end-to-end timing trial. Postfilters may return fewer than ten candidates.

Baseline top-ten document/article ordering matched the previous 74-question run. Changing dense depth to 20/50 preserved the top-ten ordering for all 74 cases. Expanding the pool alone does not improve the first ten results: it makes three missing expected articles available for subsequent selection.

## Why the four passages were missed

| ID | Expected passage | Dense rank / exact cosine rank | Metadata-filtered rank | Scoped reranked rank |
|---|---|---|---:|---:|
| Q027 | Law 33/2021, Article 6, chunk 61 | 17 / 17 | 1 | 1 |
| Q041 | Law 33/2021, Article 3, chunk 56 | 106 / 106 | 13 | 3 |
| Q068 | Law 9/2022, Article 26, chunk 240 | 14 / 14 | 13 | 3 |
| Q072 | Law 33/2021, Article 27, chunk 98 | 12 / 12 | 10 | 5 |

- Q027: all ten baseline candidates come from domestic-worker documents (seven Decision 106, two Law 9, one Resolution 92). Recruitment-office language competes with the private-sector fee prohibition. Expected-chunk distance 0.4306 versus 0.4074 at rank ten.
- Q041: all ten baseline candidates concern domestic-worker legislation. The general-law exclusion clause lies outside even the global Top-50. Its distance is 0.4153 versus 0.3151 at rank ten. A source filter brings it to rank 13, so filtering alone is insufficient at Top-10.
- Q068: nine of ten candidates already belong to the domestic regime. Termination, disputes and entitlement provisions outrank the limitation clause, so law filtering alone changes rank only from 14 to 13. Distance gap to rank ten is small (0.3568 versus 0.3511); lexical reranking promotes it.
- Q072: wage definitions/payment provisions and two domestic-worker passages precede Article 27. Distance gap is small (0.4359 versus 0.4301). General-law filtering moves the passage to the tenth position.

Exact cosine rescoring of the existing stored embeddings reproduced the expected ranks 17/106/14/12. This rules out an approximate-search omission as the explanation for those ranks in this snapshot; semantic similarity and law-regime competition are consistent with the observations. It does not prove a unique causal explanation for model similarity. All required quoted evidence for these four cases exists intact inside individual stored chunks, so a chunk-boundary repair is not supported by these checks.

## Regressions and recommendation

**Recommended first candidate: explicit-regime metadata filtering (`prefilter10`).** It improves Hit@10 from 68/72 to 70/72 and recall from 93.06% to 95.83%, recovering Q027/Q072. Across K=1/3/5/10 there are no per-question Hit, recall or reciprocal-rank regressions, including on the other 68 scored questions. Postfiltering the Top-20 pool produced the same scored improvements here and is another lightweight option.

Global reranking is less safe: Top-50 RRF loses Q004 at K=10 by displacing relevant probation Article 9 passages with other notice/termination clauses. Even Top-20 RRF, with no Hit@10 losses, worsens earlier ranks on multiple cases.

The adaptive scoped variant keeps baseline results for unspecified queries and applies metadata prefiltering plus Top-50 reranking only for explicit regimes. It reaches **72/72 Hit@10 and 100% expected-article recall**, recovering all four misses with no Hit/recall losses at K=10 on the other 68 scored questions. However, Q049/Q053/Q054 have worse reciprocal ranks, and Q049 loses Hit at K=3 and K=5. It therefore does **not** meet a blanket no-regression requirement. Keep it experimental and test held-out paraphrases, ambiguous/multi-regime questions and actual claim support before considering promotion.

No retrieval improvement has been promoted. These are corpus-specific development-set results on unreviewed keys, not proof of answer correctness, faithfulness or abstention behavior.

## Validation, protection and changed files

- **124 regression tests passed, 0 failed**: prior suite plus diagnostic specificity/redaction, strict parsing, no historical repair, separate human worksheets, query-only routing, candidate preservation, deterministic reranking, empty-index refusal, regression detection and replay isolation.
- Dataset source-quote verification and `git diff --check` passed.
- Original index byte hashes unchanged; logical contents of all collections unchanged before/after and after reopen. Chroma opened only `C:\Users\Admin\AppData\Local\Temp\compliance-rag-experiments-joio2qka\working`.
- **36/36 protected artifacts, all 13 pre-existing run/report artifacts, and production retrieval/generation/citation/UI files unchanged.** Evidence: `runs/phase41-baseline-01.json` and `runs/phase41-integrity-01.json`.
- Updated evaluation files: `eval_judge.py`, `eval_answers.py`, `README.md`. Added `eval_review.py`, `retrieval_experiments.py`, `tests/test_phase41.py` and new reports/artifacts. No new dependencies or infrastructure.

## Artifacts

- `runs/phase41-retrieval-01.json`: isolated queries, candidates, scores, distances, deep diagnostics, timings, fingerprints and integrity.
- `runs/phase41-scoped-replay-01.json`: adaptive gate, original-source hash, all per-K regression IDs and reused timings.
- `runs/phase41-judge-diagnosis-01.json`: historical uncertainty, confirmed diagnostic loss and implemented fixes.
- `runs/phase41-report-01.json`: machine-readable combined summary.
- `runs/phase41-manual-review-01.json` and `reports/phase41-manual-review-01.md`: review worksheet; all human verdicts pending.
