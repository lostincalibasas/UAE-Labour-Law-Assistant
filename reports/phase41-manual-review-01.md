# Phase 4.1 manual-review worksheet

Fill human_review only; preserve automated_snapshot and original artifacts. Unknown fields stay null. No historical repair or legal correctness inferred from IDs.

Exact historical schema errors cannot be reconstructed: rejected response bodies were not retained.
The companion JSON contains all exact evidence excerpts and blank, separate human-review fields.

## Q044

Judge schema invalid. Exact violation unavailable: response and validator detail were not retained. Review answer, required facts, and each cited claim independently.

**Question:** How many days of paid sick leave does a domestic worker get per year?

**Saved answer (untrusted text):**

```text
A domestic worker is entitled to 30 days of sick leave per year of service, either continuous or intermittent, subject to a medical report from an approved health authority showing the need for such leave. The first 15 days are paid in full, and the next 15 days are paid at half pay [E1].
```

**Original automated judgment:**

```json
{
  "status": "evaluation_failure",
  "error": "judge_schema_invalid",
  "scores": {
    "pass": false
  }
}
```

**Unchanged required facts:**

- Fact 0: 30 days per year of service, continuous or intermittent, on a medical report from an approved authority.
- Fact 1: First 15 days paid in full, next 15 days at half pay.
- Fact 2: No payment if the worker's behaviour contributed to the illness.

**Evidence map** (full exact excerpts in companion JSON):

- [E1] Federal Decree-Law No. 9 of 2022 / Article 10
- [E2] Federal Decree-Law No. 9 of 2022 / Article 10
- [E3] Federal Decree-Law No. 9 of 2022 / Article 19
- [E4] Federal Decree-Law No. 9 of 2022 / Article 10
- [E5] Federal Decree-Law No. 9 of 2022 / Article 9
- [E6] Cabinet Decision No. 106 of 2022 / Article 7
- [E7] Cabinet Decision No. 106 of 2022 / Article 8
- [E8] Federal Decree-Law No. 33 of 2021 / Article 31
- [E9] Federal Decree-Law No. 9 of 2022 / Article 8
- [E10] Federal Decree-Law No. 33 of 2021 / Article 32

**Human review — pending:**

- Reviewer/date:
- Answer correctness and fact coverage:
- Claim-to-citation support and applicable employment regime:
- Evidence sufficiency / appropriateness of abstention:
- Answer-key relevance / proposed correction (do not edit the dataset):
- Verdict / rationale:

## Q049

Judge schema invalid. Exact violation unavailable. Only one of two expected articles was retrieved; review passport rule and the separately requested penalty against the captured evidence.

**Question:** Can an employer keep a domestic worker's passport, and is there a fine?

**Saved answer (untrusted text):**

```text
An employer may not keep a domestic worker's passport. The domestic worker must be allowed to retain all official documents [E1]. The evidence provided does not specify a fine for an employer who retains a domestic worker's passport.
```

**Original automated judgment:**

```json
{
  "status": "evaluation_failure",
  "error": "judge_schema_invalid",
  "scores": {
    "pass": false
  }
}
```

**Unchanged required facts:**

- Fact 0: The domestic worker should be allowed to retain all official documents.
- Fact 1: Administrative fine of AED 500 per domestic worker for withholding identification documents.

**Evidence map** (full exact excerpts in companion JSON):

- [E1] Federal Decree-Law No. 9 of 2022 / Article 11
- [E2] Federal Decree-Law No. 9 of 2022 / Article 27
- [E3] Cabinet Decision No. 106 of 2022 / Article 4
- [E4] Cabinet Decision No. 106 of 2022 / Article 11
- [E5] Cabinet Decision No. 106 of 2022 / Article 4
- [E6] Cabinet Decision No. 106 of 2022 / Article 4
- [E7] Federal Decree-Law No. 9 of 2022 / Article 5
- [E8] Federal Decree-Law No. 9 of 2022 / Article 21
- [E9] Cabinet Decision No. 106 of 2022 / Article 10
- [E10] Federal Decree-Law No. 9 of 2022 / Article 12

**Human review — pending:**

- Reviewer/date:
- Answer correctness and fact coverage:
- Claim-to-citation support and applicable employment regime:
- Evidence sufficiency / appropriateness of abstention:
- Answer-key relevance / proposed correction (do not edit the dataset):
- Verdict / rationale:

## Q073

Judge schema invalid. Exact violation unavailable. Verify the observed fallback against the out-of-scope key; do not interpret judge rejection as a failure to abstain.

**Question:** How much does a residence visa for a domestic worker cost?

**Saved answer (untrusted text):**

```text
I don't have enough information in the available documents to answer this confidently.
```

**Original automated judgment:**

```json
{
  "status": "evaluation_failure",
  "error": "judge_schema_invalid",
  "scores": {
    "pass": false
  }
}
```

**Unchanged required facts:**

- Fact 0: States that the provided documents do not contain visa or residence fee amounts.

**Evidence map** (full exact excerpts in companion JSON):

- [E1] Federal Decree-Law No. 9 of 2022 / Article 10
- [E2] Federal Decree-Law No. 9 of 2022 / Article 11
- [E3] Federal Decree-Law No. 9 of 2022 / Article 5
- [E4] Federal Decree-Law No. 9 of 2022 / Article 10
- [E5] Federal Decree-Law No. 9 of 2022 / Article 27
- [E6] Cabinet Decision No. 106 of 2022 / Article 6
- [E7] Federal Decree-Law No. 9 of 2022 / Article 20
- [E8] Cabinet Decision No. 106 of 2022 / Article 6
- [E9] Federal Decree-Law No. 9 of 2022 / Article 3
- [E10] Cabinet Decision No. 106 of 2022 / Article 20

**Human review — pending:**

- Reviewer/date:
- Answer correctness and fact coverage:
- Claim-to-citation support and applicable employment regime:
- Evidence sufficiency / appropriateness of abstention:
- Answer-key relevance / proposed correction (do not edit the dataset):
- Verdict / rationale:

## Q041

Answer-key scope review: are government and armed-forces/police exclusions necessary for the domestic-worker applicability question? Expected facts remain unchanged.

**Question:** Does the main labour law apply to domestic workers?

**Saved answer (untrusted text):**

```text
I don't have enough information in the available documents to answer this confidently.
```

**Original automated judgment:**

```json
{
  "facts": [
    {
      "id": 0,
      "verdict": "missing",
      "evidence_ids": [],
      "reason": "No supplied passage states that domestic workers are excluded from the main labour law (Federal Decree-Law No. 33 of 2021). The evidence concerns Federal Decree-Law No. 9 of 2022 on domestic workers and does not address the scope exclusion under the main labour law."
    },
    {
      "id": 1,
      "verdict": "missing",
      "evidence_ids": [],
      "reason": "No supplied passage mentions government employees or armed forces/police/security employees or their exclusion from the main labour law."
    }
  ],
  "forbidden": [],
  "claims": [],
  "unsupported_claims": [],
  "evidence_sufficient": false,
  "answer_correct": false,
  "status": "valid",
  "scores": {
    "fact_coverage": 0.0,
    "facts_present": 0,
    "facts_total": 2,
    "contradicted": 0,
    "forbidden_triggered": 0,
    "unsupported_claims": 0,
    "wrong_law_claims": 0,
    "claims_total": 0,
    "claims_supported": 0,
    "pass": false
  }
}
```

**Unchanged required facts:**

- Fact 0: No. Domestic workers are excluded from the Decree-Law's scope.
- Fact 1: Government employees and armed forces/police/security employees are also excluded.

**Evidence map** (full exact excerpts in companion JSON):

- [E1] Cabinet Decision No. 106 of 2022 / Article 11
- [E2] Federal Decree-Law No. 9 of 2022 / Article 3
- [E3] Federal Decree-Law No. 9 of 2022 / Article 12
- [E4] Federal Decree-Law No. 9 of 2022 / Article 11
- [E5] Federal Decree-Law No. 9 of 2022 / Article 11
- [E6] Federal Decree-Law No. 9 of 2022 / Article 6
- [E7] Federal Decree-Law No. 9 of 2022 / Article 12
- [E8] Federal Decree-Law No. 9 of 2022 / Article 14
- [E9] Federal Decree-Law No. 9 of 2022 / Article 9
- [E10] Federal Decree-Law No. 9 of 2022 / Article 11

**Human review — pending:**

- Reviewer/date:
- Answer correctness and fact coverage:
- Claim-to-citation support and applicable employment regime:
- Evidence sufficiency / appropriateness of abstention:
- Answer-key relevance / proposed correction (do not edit the dataset):
- Verdict / rationale:

## Q068

Answer-key scope review: is the judicial-fee exemption necessary for a question about the filing time limit? Expected facts remain unchanged.

**Question:** How long does a domestic worker have to sue for her entitlements after the job ends?

**Saved answer (untrusted text):**

```text
I don't have enough information in the available documents to answer this confidently.
```

**Original automated judgment:**

```json
{
  "facts": [
    {
      "id": 0,
      "verdict": "missing",
      "evidence_ids": [],
      "reason": "No supplied passage states the three-month limitation period for domestic workers' claims after employment ends."
    },
    {
      "id": 1,
      "verdict": "missing",
      "evidence_ids": [],
      "reason": "No supplied passage states that domestic workers' actions are exempt from judicial fees."
    }
  ],
  "forbidden": [
    {
      "id": 0,
      "triggered": false,
      "reason": "The answer does not state any limitation period, including one year."
    }
  ],
  "claims": [],
  "unsupported_claims": [],
  "evidence_sufficient": false,
  "answer_correct": false,
  "status": "valid",
  "scores": {
    "fact_coverage": 0.0,
    "facts_present": 0,
    "facts_total": 2,
    "contradicted": 0,
    "forbidden_triggered": 0,
    "unsupported_claims": 0,
    "wrong_law_claims": 0,
    "claims_total": 0,
    "claims_supported": 0,
    "pass": false
  }
}
```

**Unchanged required facts:**

- Fact 0: Not heard after three months from the date the employment relationship ended.
- Fact 1: Domestic workers' actions are exempt from judicial fees.

**Evidence map** (full exact excerpts in companion JSON):

- [E1] Cabinet Decision No. 106 of 2022 / Article 10
- [E2] Federal Decree-Law No. 9 of 2022 / Article 18
- [E3] Federal Decree-Law No. 9 of 2022 / Article 19
- [E4] Federal Decree-Law No. 33 of 2021 / Article 53
- [E5] Federal Decree-Law No. 9 of 2022 / Article 8
- [E6] Federal Decree-Law No. 9 of 2022 / Article 10
- [E7] Federal Decree-Law No. 9 of 2022 / Article 19
- [E8] Cabinet Decision No. 106 of 2022 / Article 10
- [E9] Federal Decree-Law No. 9 of 2022 / Article 10
- [E10] Cabinet Decision No. 106 of 2022 / Article 9

**Human review — pending:**

- Reviewer/date:
- Answer correctness and fact coverage:
- Claim-to-citation support and applicable employment regime:
- Evidence sufficiency / appropriateness of abstention:
- Answer-key relevance / proposed correction (do not edit the dataset):
- Verdict / rationale:
