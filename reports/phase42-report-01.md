# Phase 4.2 ? query-driven law-regime retrieval

Experimental implementation and offline validation complete. **No production promotion, API calls, reranking, hybrid search or embedding rebuild.**

## Runtime label-independence audit

Phase 4.1 `route(question)` reads only question text; `allowed_sources(regime)` is a static source-name map. It does not read expected articles, fact labels or question IDs. However, its rules were developed against known misses, so prior development-set results alone were not independent evidence of generalization.

Its weaknesses are deterministic: general-law signals take priority over domestic signals, and bare domestic/household tokens trigger domestic routing. This can filter mixed questions or misread domestic airlines/companies and household-goods contexts.

The new runtime boundary is `select_regime(question, source_documents)`. It accepts no answer keys. `retrieve_variants()` finishes routing and queries before the separate `score_case()` sees any labels. Regression tests verify this boundary and confirm that changing score labels cannot change retrieved candidates.

## Proposed selection design

1. Normalize case, Unicode and dash variants; recognize explicit private-sector/general/main-law wording, domestic-worker/household-staff wording, and full document number/year references. Article numbers alone do not determine a law.
2. Match only source names present in the isolated index against a reviewed corpus catalog: Law 33/2021 is general; Law 9/2022, Decision 106/2022 and Resolution 92/2022 are domestic. Unknown metadata disables filtering pending catalog review; missing target-regime sources also produce no filter.
3. Treat mixed regime signals, unclear employment, negation, changed employment context, quoted regime text, routing instructions and recognized outside/special jurisdictions conservatively. Keep the unfiltered Top-10 baseline instead of guessing. Unsupported language with no recognized signal also remains unfiltered.
4. For an explicit single regime, construct an exact source-document `$in` filter from catalog names. User text is never inserted as a query expression. BGE model, normalization, query prefix, cosine order and Top-10 limit are unchanged.

No-filter is a retrieval decision, not an answer abstention. The experiment retains the exact baseline candidate list for every mixed/uncertain query. This is an English heuristic and cannot prove legal applicability or handle every indirect reference, jurisdiction, negation or adversarial phrasing.

## Evaluation method

- Existing suite: all 74 questions, of which 72 have expected articles. The original dataset and expected facts are unchanged.
- New challenge suite: 40 frozen cases covering paraphrases, explicit document references, mixed regimes, ambiguity, negation, changed employment, quoted/instruction-like text, lexical decoys, special/foreign jurisdictions and Arabic. Sixteen have provisional article anchors; all 40 have conservative routing-policy expectations.
- The challenge suite was locally authored alongside the selector and frozen before retrieval execution. No rules were tuned after seeing its retrieval results. **It is not an independently authored or human-validated holdout.** Article references were checked for corpus presence, not legal correctness.
- One cached BGE query embedding per question, reused across original baseline, Phase 4.1 and Phase 4.2 arms. Identical filter queries are shared within the comparison. Distinct query order rotates to reduce fixed cache-order bias. No lexical scoring, reranking, or result fusion is called.
- Hit@K is presence of any expected document/article among the first K chunks. Recall is mean fraction of expected articles found per question. MRR uses unique document/article rank, matching the historical evaluator. Cases without expected articles are excluded from these denominators.

## Retrieval comparison

| Suite | Arm | Hit@10 | Article recall@10 | MRR@10 | Median query ms | Median encoding + query ms |
|---|---|---:|---:|---:|---:|---:|
| existing74 | baseline | 68/72 (94.44%) | 93.06% | 0.8303 | 7.17 | 242.83 |
| existing74 | phase41 | 70/72 (97.22%) | 95.83% | 0.8641 | 8.54 | 244.46 |
| existing74 | phase42 | 70/72 (97.22%) | 95.83% | 0.8641 | 8.54 | 245.07 |
| challenge40 | baseline | 13/16 (81.25%) | 78.12% | 0.5208 | 8.42 | 410.35 |
| challenge40 | phase41 | 16/16 (100.00%) | 90.62% | 0.6380 | 11.59 | 411.84 |
| challenge40 | phase42 | 15/16 (93.75%) | 90.62% | 0.6458 | 9.99 | 412.10 |

Initial model loading took 80.94 seconds and is excluded from the table. Median routing-bundle overhead was 0.239 ms on the existing suite and 0.196 ms on challenges; this measures both selectors together, not the new selector alone. Timings are single-run observations under variable machine load, not statistically significant speed claims. Different suite latencies should not be interpreted as strategy speed differences.

Phase 4.2 preserved the Phase 4.1 gains on the original set: Q027 and Q072 are recovered; Q041 and Q068 remain misses. Baseline Top-10 document/article ordering reproduced the previous 74-question output exactly.

On new scored questions, G01 and L03 recruitment-cost paraphrases improve over baseline. M03 (whether the general law covers domestic workers) remains a miss because both regimes are retained. Phase 4.1 gets 16/16 Hit@10 versus Phase 4.2 15/16, but it also removes required domestic sources on mixed comparisons M01/M02. This illustrates why higher Hit@10 alone is not a sufficient safety criterion.

## Ranking and selection errors

**Compared with the original BGE baseline, Phase 4.2 has no per-question Hit, recall or reciprocal-rank regressions at K=1, 3, 5 or 10 in either suite.** This is measured on these samples, not a guarantee for unseen questions.

| Challenge routing check | Baseline | Phase 4.1 | Phase 4.2 |
|---|---:|---:|---:|
| Matches authored policy | 27/40 | 15/40 | 40/40 |
| Filters contrary to authored policy | 0/40 | 21/40 | 0/40 |
| Expected-source exclusions | 0 | 2 (M01/M02) | 0 |

The baseline intentionally never filters; its 13 policy mismatches are missed filtering opportunities, not unsafe selections. Likewise, the proposed 40/40 score is agreement with provisional safety rules, not validated legal-regime accuracy. No regime-accuracy denominator exists for the original 74 questions; there we report expected-source exclusions and retrieval metrics rather than claiming every selection is legally correct.

Phase 4.1 unsafe-filter IDs under the challenge policy: M01, M02, M03, A01, A03, N01, N02, N03, N04, X01, X02, X03, L01, L02, L04, O01, O02, O03, X05, L05, N05.

Representative findings:

- Mixed comparisons M01/M02: Phase 4.1 chooses general law and excludes the domestic article. Phase 4.2 keeps both sources available, eliminating those recall regressions.
- M03 and original Q041: Phase 4.2 treats both-regime applicability wording as mixed. This is conservative but does not solve the scope-clause retrieval miss.
- A01/A03 and N01?N05: uncertainty, negation or changed context prevent a forced regime choice. Original Q066 also falls back to unfiltered search under the conservative negation rule; its scored metrics are unchanged.
- L01/L02/L04/L05: domestic airline, domestic violence, domestic subsidiary and domestic company do not identify domestic-worker legislation. L03 retains a general filter despite household-goods vocabulary.
- X01?X03/X05: routing instructions, conflicting signals and quoted regime context cannot force a narrowed search. O01?O04 retain unfiltered search for special/foreign jurisdictions or unsupported language.
- Explicit document cases G04/D03/D05/D06 are recognized by law number and year; the older selector left these unfiltered.

The proposed selector filters 39/74 existing questions; 34 are uncertain and one mixed. On challenges it filters 13/40, leaves 22 uncertain and five mixed. All 35 existing and 27 challenge no-filter cases exactly preserve baseline candidates. Neither absence of a filter nor presence of an expected article establishes answer sufficiency.

## Unresolved human review

The Phase 4.1 worksheet was inspected and preserved. All five human verdicts remain null; no human legal review has been recorded.

- **Q041 requires answer-key review:** whether government/armed-forces/police exclusions overconstrain a question specifically about domestic-worker applicability.
- **Q068 requires answer-key review:** whether judicial-fee exemption is required for a question specifically about the filing time limit.
- Q044/Q049/Q073 historical judge failures also remain unresolved; their original outcomes were not repaired or rejudged.

See [preserved manual-review worksheet](phase41-manual-review-01.md). New challenge article keys are also provisional. No existing answer key was changed.

## Recommendation

**Not yet ready for unconditional production promotion.** The selector is a promising lower-risk experimental replacement for the Phase 4.1 keyword priority rule: it retains the measured original-suite gains and avoids forced filters on the designed ambiguous/adversarial cases.

Before a separately approved production trial, obtain blinded, human-reviewed cases from unseen wording and employment contexts; include mixed-law comparisons, unfamiliar jurisdictions, colloquial occupations, indirect negation, quoted text and non-English questions. Resolve Q041/Q068 key scope and validate false-filter rates and relevant-evidence exclusion independently. Conservative fallback can be retained as a safeguard, but these small, locally authored samples do not establish generalization. No paid answer-quality evaluation or production changes are authorized by this report.

## Validation and artifact protection

- **145 regression tests passed; 0 failed.** Coverage includes explicit/mixed/uncertain selection, negation, quotes/instructions, lexical decoys, metadata fail-closed behavior, label separation, no-filter identity, baseline query settings, empty collections, path isolation, non-overwriting outputs and unsafe-filter reporting.
- Dataset quote verification and `git diff --check` passed.
- Zero API requests; no reranking/hybrid retrieval; no stored embedding rebuild. All Chroma opens used only `C:\Users\Admin\AppData\Local\Temp\compliance-rag-regimes-gddrte7a\working`.
- Original index hashes and all collection logical fingerprints remained unchanged before/after and after reopen.
- **All 36 protected artifacts and all 22 pre-existing run/report artifacts unchanged.** Production retrieval, generation, citation handling and UI files are byte-identical to the baseline.
- Code/fixture hashes confirm that the selector and frozen challenge fixture were unchanged after execution. Separate source/dataset/catalog/index fingerprints are recorded.

Added `regime_selector.py`, `phase42_eval.py`, `tests/test_phase42.py`, and `tests/fixtures/phase42_challenge.json`; updated README documentation. No new dependencies.

## Saved outputs

- `runs/phase42-comparison-01.json`: both suites, all arm selections, ranked IDs/metadata/distances/text hashes, scores, timing, fingerprints and index checks.
- `runs/phase42-routing-audit-01.json`: label-independence audit and pending human-review flags.
- `runs/phase42-baseline-01.json` / `runs/phase42-integrity-01.json`: artifact and production-file hashes.
- `runs/phase42-report-01.json`: combined machine-readable report.
