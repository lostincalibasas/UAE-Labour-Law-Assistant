# Controlled ten-question DeepSeek pilot

Completed using `deepseek-chat` for both generation and judging. Results are provisional, not human-validated legal correctness. No production code or persistent API configuration was changed.

## Execution and protection

- Exactly **10 generation and 10 judge requests**, SDK retries disabled. No expansion to 74 questions and no extra API probes or retries.
- One production top-10 BGE retrieval per question, no diagnostic-depth option. The same captured evidence was used for generation, reference validation and judging.
- Every saved evidence hash rechecked; all accepted citation IDs, document/article metadata and exact excerpts re-resolved successfully: **5 references across 4 answers**.
- Chroma opened only the guarded, byte-verified working copy at `C:\Users\Admin\AppData\Local\Temp\compliance-rag-eval-1rp1wsqx\working`. All collection logical fingerprints were stable before/after and after reopen.
- **All 36 protected artifacts unchanged**. Application code hashes unchanged. No original index client, embedding rebuild, or overwritten result.

## Provisional metrics

| Measure | Result | Denominator / qualification |
|---|---|---|
| Expected-article Hit@10 | 4/8 (50%) | Eight answerable items; deliberately difficult pilot, not representative of the 74-question suite |
| Expected-article macro recall@10 | 43.75% | Q049 retrieved one of two expected articles |
| Judge answer_correct | 4/7 (57.1%) | Seven schema-valid judgments; includes correct abstentions |
| Strict automated pass | 2/7 (28.6%) | Q010 and Q074; three invalid judgments are evaluation failures, not passes |
| Required-fact coverage | 3/10 (30%) | Required facts across seven valid judgments, including the Q074 abstention fact |
| Faithfulness / citation semantic support | 3/3 assessed claims | Only Q001 and Q010 substantive answers had valid judges; Q044/Q049 semantics unknown |
| Unsupported / contradicted / wrong-law claims | 0 / 0 / 0 | Only three assessed claims; not evidence of zero errors across the whole pilot |
| Citation identity | 4/4 substantive answers; 5/5 references | Six abstentions had no citations; zero invented-ID or missing-citation rejections |
| Dataset forbidden-source citation flags | 0/10 | Deterministic document/article comparison, not semantic proof |
| Out-of-scope fallback observed | 2/2 | Q073 and Q074; only Q074 has a valid judge |
| Unnecessary abstention | 0/4 assessed answerable abstentions | Judge found insufficient evidence in all four |
| Retrieval / generation operational failures | 0 / 0 | All ten retrieval and generation requests completed |
| Judge failures | 3/10 (30%) | Q044, Q049, Q073: judge_schema_invalid; never scored as passing |

The existing machine report shows out_of_scope_abstention=1/2 because it classifies Q073 as evaluation_failure before checking abstention. This is a judge-confirmed outcome count; it must not be interpreted as the generator failing to abstain on Q073. Both out-of-scope responses used the fallback.

## Individual results and timing

| ID | Retrieval@10 | Response / citations | Judge / fact coverage | Retrieval s | Generation s | Judge s |
|---|---|---|---|---:|---:|---:|
| Q001 | Hit | ok; valid IDs | No strict pass; 1/2 facts | 25.996 | 2.779 | 2.184 |
| Q010 | Hit | ok; valid IDs | Pass; 1/1 facts | 0.095 | 1.122 | 2.227 |
| Q027 | Miss | insufficient_evidence; fallback | No strict pass; 0/1 facts | 0.100 | 0.934 | 1.299 |
| Q041 | Miss | insufficient_evidence; fallback | No strict pass; 0/2 facts | 0.097 | 1.075 | 1.446 |
| Q044 | Hit | ok; valid IDs | Invalid schema; unknown | 0.119 | 1.231 | 2.331 |
| Q049 | Hit; partial recall | ok; valid IDs | Invalid schema; unknown | 0.099 | 1.231 | 2.218 |
| Q068 | Miss | insufficient_evidence; fallback | No strict pass; 0/2 facts | 0.124 | 0.842 | 1.629 |
| Q072 | Miss | insufficient_evidence; fallback | No strict pass; 0/1 facts | 0.113 | 1.349 | 1.351 |
| Q073 | N/A (out of scope) | insufficient_evidence; fallback | Invalid schema; unknown | 0.113 | 0.579 | 1.503 |
| Q074 | N/A (out of scope) | insufficient_evidence; fallback | Pass; 1/1 facts | 0.116 | 1.172 | 1.242 |

Generation mean **1.231 s**, median **1.147 s**; judge mean **1.743 s**, median **1.566 s**. Retrieval median **0.113 s**; first query **25.996 s**, including model initialization. These are client-side phase timings, not isolated server-compute latency.

## Failure analysis and manual review

- **Q001**: Correct direct answer; 1/2 required facts. New-employer recruitment/contracting cost compensation omitted.
- **Q010**: Automated strict pass; two verified references to Article 43.
- **Q027**: Expected article missed; abstention supported by judge evidence_sufficient=false.
- **Q041**: Expected article missed; evidence-limited abstention. HUMAN ANSWER-KEY REVIEW REQUIRED.
- **Q044**: Answer and citation identity accepted; judge schema invalid, semantic quality unknown.
- **Q049**: Only 1/2 expected articles retrieved; answer citation accepted; judge schema invalid.
- **Q068**: Expected article missed; evidence-limited abstention. HUMAN ANSWER-KEY REVIEW REQUIRED.
- **Q072**: Expected article missed; evidence-limited abstention on an answerable partial case.
- **Q073**: Observed correct fallback for an out-of-scope item; judge schema invalid.
- **Q074**: Out-of-scope abstention; automated strict pass.

Four expected-article misses coincided with evidence-limited abstentions: Q027/Q041/Q068/Q072. These are retrieval/evidence coverage limitations, not service failures. Q001 is a generation/key-fact coverage gap relative to the current rubric, despite sufficient retrieved evidence. Q044/Q049 cannot be categorized as generation-quality successes or failures because their judge outputs were rejected.

Judge limitations: invalid response bodies and field-level validation diagnostics are not retained by the current evaluator. The saved code judge_schema_invalid cannot establish which field was malformed or omitted; no incomplete response was treated as passing. The judge marked Q027 abstention correct but Q041/Q068/Q072 abstentions incorrect despite finding insufficient evidence in all four, indicating a rubric/calibration issue for manual review. Using the same model for both roles can produce correlated errors.

## Recommended next steps

1. Manually review all ten saved responses, prioritizing the three rejected judgments and the Q041/Q068 answer keys. Q041 includes exclusions beyond domestic workers; Q068 includes court-fee facts beyond the time-limit question. Review Q001 required compensation fact for relevance to its focused notice question.
2. Before another paid run, improve sanitized judge validation diagnostics and calibrate abstention grading. Keep strict rejection; do not loosen validation merely to improve pass rate. No evaluator changes were made during this pilot.
3. Use the established deeper-rank diagnostics to design a separately approved retrieval improvement experiment. Preserve this pilot as the baseline; do not automatically expand to all 74 questions.

## Artifacts

- `runs/phase4-live-pilot-01.json`: complete responses, evidence, metadata, citations, retrieval scores, judgments/errors, fingerprints, timings and request counters.
- `runs/phase4-live-metrics-01.json`: existing offline aggregator output; interpretation caveat above.
- `runs/phase4-live-baseline-01.json` and `runs/phase4-live-integrity-01.json`: protected artifact and application-code hashes.
- `runs/phase4-live-review-01.json`: supplemental observations and review flags, separate from automated judgments. Human reviewer verdicts remain pending.
- `runs/live_pilot_01.py`: execution-only launcher; credentials mapped in process memory, never printed or saved.
