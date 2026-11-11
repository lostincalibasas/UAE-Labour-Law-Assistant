"""Offline metrics. No model imports, credentials, retrieval, or API requests."""
from collections import Counter

REVIEW_KEYS = {'Q041', 'Q068'}


def classify(row):
    response = row.get('response', {})
    if row.get('retrieval_error'):
        return 'retrieval_operational_failure'
    if response.get('status') == 'operational_error':
        return 'generation_operational_failure'
    if not response:
        return 'not_generated'
    validation = response.get('citation_validation', {}).get('status')
    if validation in {'invalid_citations', 'missing_citations', 'legacy_unverified'}:
        return 'citation_rejection'
    judge = row.get('judge', {})
    if judge.get('status') == 'evaluation_failure':
        return 'evaluation_failure'
    if response.get('status') == 'insufficient_evidence':
        if row['answerable'] is False:
            return 'legitimate_abstention'
        if judge.get('status') != 'valid':
            return 'abstention_requires_review'
        return 'unnecessary_abstention' if judge['evidence_sufficient'] else 'evidence_limited_abstention'
    if row['answerable'] is False:
        return 'out_of_scope_answer'
    if judge.get('status') != 'valid':
        return 'unjudged_answer'
    if judge['scores']['pass']:
        return 'automated_pass'
    if not judge['evidence_sufficient']:
        return 'evidence_limited_answer_failure'
    return 'generation_quality_failure'


def ratio(n, d):
    return {'numerator': n, 'denominator': d, 'value': n / d if d else None}


def make_report(run):
    rows = run['rows']
    judged = [r for r in rows if r.get('judge', {}).get('status') == 'valid']
    responses = [r for r in rows if r.get('response') and r['response']['status'] != 'operational_error']
    answers = [r for r in responses if r['response']['status'] == 'ok']
    claims = [c for r in judged for c in r['judge']['claims']]
    cited_claims = [c for c in claims if c['evidence_ids']]
    facts = [f for r in judged for f in r['judge']['facts']]
    out_scope = [r for r in responses if not r['answerable']]
    answerable_judged = [r for r in judged if r['answerable']]
    law_flags = [r for r in responses if 'citations' in r]
    metrics = {
        'answer_correctness': ratio(sum(r['judge']['answer_correct'] for r in judged), len(judged)),
        'strict_answer_pass': ratio(sum(r['judge']['scores']['pass'] for r in judged), len(judged)),
        'key_fact_coverage_micro': ratio(sum(f['verdict'] == 'present' for f in facts), len(facts)),
        'claim_faithfulness': ratio(sum(c['verdict'] == 'supported' for c in claims), len(claims)),
        'citation_semantic_precision': ratio(sum(c['verdict'] == 'supported' and not c['wrong_law'] for c in cited_claims), len(cited_claims)),
        'citation_claim_coverage': ratio(len(cited_claims), len(claims)),
        'citation_identity_acceptance': ratio(len(answers), len(responses)),
        'wrong_law_claim_rate': ratio(sum(c['wrong_law'] for c in claims), len(claims)),
        'contradicted_claim_rate': ratio(sum(c['verdict'] == 'contradicted' for c in claims), len(claims)),
        'out_of_scope_abstention': ratio(sum(classify(r) == 'legitimate_abstention' for r in out_scope), len(out_scope)),
        'unnecessary_abstention': ratio(sum(classify(r) == 'unnecessary_abstention' for r in answerable_judged), len(answerable_judged)),
        'forbidden_source_citation_rate': ratio(sum(bool(r['citations']['wrong_law_flag']) for r in law_flags), len(law_flags)),
        'judge_failure_rate': ratio(sum(r.get('judge', {}).get('status') == 'evaluation_failure' for r in rows),
                                    sum('judge' in r for r in rows)),
    }
    retrieval = {}
    for k in run['config']['ks']:
        scored = [r['retrieval'][str(k)] for r in rows if str(k) in r.get('retrieval', {})]
        retrieval[str(k)] = {'denominator': len(scored), **{
            name: sum(m[name] for m in scored) / len(scored) if scored else None
            for name in ('hit', 'rr', 'recall', 'precision')}}
    review = []
    for row in rows:
        reasons = []
        if row['id'] in REVIEW_KEYS:
            reasons.append('human_answer_key_review_required; expected facts unchanged')
        outcome = classify(row)
        if outcome not in {'not_generated', 'automated_pass', 'legitimate_abstention'}:
            reasons.append(outcome)
        if row.get('retrieval', {}).get('10', {}).get('hit') == 0:
            reasons.append('expected_article_missing_at_10')
        if reasons:
            review.append({'id': row['id'], 'reasons': reasons})
    return {
        'schema_version': 1, 'questions': len(rows), 'metrics': metrics, 'retrieval': retrieval,
        'requests': run.get('requests'), 'fingerprints': run.get('fingerprints'),
        'isolation': run.get('isolation'), 'original_hashes_unchanged': run.get('original_hashes_unchanged'),
        'outcomes': dict(Counter(classify(r) for r in rows)), 'manual_review_candidates': review,
        'manual_verdicts': 'Separate audit artifacts; never merged into automated judgments.',
        'definitions': {
            'retrieval': 'Top-k chunks, deduplicated (document, article); RR uses unique-article rank. Only cases with expected articles and successful retrieval enter denominators.',
            'answer_correctness': 'Judge answer_correct / schema-valid judgments; invalid/missing judgments excluded and reported separately.',
            'key_fact_coverage_micro': 'Present rubric facts / all required facts in schema-valid judgments.',
            'claim_faithfulness': 'Supported extracted claims / all extracted claims in valid judgments; uncited claims count as unsupported.',
            'citation_identity_acceptance': 'Responses accepted by deterministic ID validation / non-operational generated responses, including abstentions. Not semantic accuracy.',
            'citation_semantic_precision': 'Supported, correctly attributed cited claims / cited claims assessed by a valid judge.',
            'abstention': 'Two fully unanswerable items measured separately; partial items remain answerable. Citation rejection and operational failure are never legitimate abstention.',
            'unnecessary_abstention': 'Abstentions with judge evidence_sufficient=true / all schema-valid judged answerable items.',
            'forbidden_source_citation_rate': 'Responses citing a dataset must_not_cite document/article / non-operational responses with citation checks. A dataset flag, not a semantic wrong-law finding.',
            'causality': 'Expected-article misses are retrieval signals, not proof of insufficient evidence. Failure attribution uses judge evidence_sufficient when available.',
        },
        'limitations': ['All answer keys remain unreviewed LLM drafts; Q041 and Q068 need scope review.',
                       'Judge semantics and claim enumeration require manual calibration; deterministic schema checks cannot prove correctness or complete claim extraction.',
                       'Zero denominators mean not evaluated, never zero accuracy. No live answer quality conclusions from retrieval-only runs.'],
    }


def markdown(report):
    lines = ['# Phase 4 offline evaluation', '', f"Questions: {report['questions']}", '',
             '| K | Scored | Hit | MRR | Recall | Precision |', '|---|---|---|---|---|---|']
    for k, m in report['retrieval'].items():
        values = ['N/A' if m[n] is None else f'{m[n]:.4f}' for n in ('hit', 'rr', 'recall', 'precision')]
        lines.append(f"| {k} | {m['denominator']} | " + ' | '.join(values) + ' |')
    lines += ['', '## Answer metrics', '', '| Metric | Numerator / denominator | Value |', '|---|---|---|']
    for name, m in report['metrics'].items():
        value = 'Not evaluated' if m['value'] is None else f"{m['value']:.4f}"
        lines.append(f"| {name} | {m['numerator']} / {m['denominator']} | {value} |")
    lines += ['', '## Outcomes', ''] + [f'- {k}: {v}' for k, v in report['outcomes'].items()]
    lines += ['', '## Manual review candidates', ''] + [f"- {r['id']}: {'; '.join(r['reasons'])}" for r in report['manual_review_candidates']]
    lines += ['', '## Definitions', ''] + [f'- {k}: {v}' for k, v in report['definitions'].items()]
    lines += ['', '## Limitations', ''] + [f'- {v}' for v in report['limitations']]
    return '\n'.join(lines) + '\n'
