"""Create an offline worksheet; never rejudge or modify historical outcomes."""
import argparse
import hashlib
import json
from pathlib import Path

from artifact_io import require_new_output, write_new_json
from index_paths import disjoint

REVIEW_IDS = ('Q044', 'Q049', 'Q073', 'Q041', 'Q068')
CONCERNS = {
    'Q044': 'Judge schema invalid. Exact violation unavailable: response and validator detail were not retained. Review answer, required facts, and each cited claim independently.',
    'Q049': 'Judge schema invalid. Exact violation unavailable. Only one of two expected articles was retrieved; review passport rule and the separately requested penalty against the captured evidence.',
    'Q073': 'Judge schema invalid. Exact violation unavailable. Verify the observed fallback against the out-of-scope key; do not interpret judge rejection as a failure to abstain.',
    'Q041': 'Answer-key scope review: are government and armed-forces/police exclusions necessary for the domestic-worker applicability question? Expected facts remain unchanged.',
    'Q068': 'Answer-key scope review: is the judicial-fee exemption necessary for a question about the filing time limit? Expected facts remain unchanged.',
}


def create_worksheet(input_path, dataset, output, markdown_path):
    output, markdown_path = require_new_output(output), require_new_output(markdown_path)
    if not disjoint(output) or not disjoint(markdown_path) or output.resolve() == markdown_path.resolve():
        raise ValueError('Worksheet destinations must be separate and outside protected indexes')
    original = Path(input_path).read_bytes()
    source = json.loads(original)
    questions = {q['id']: q for q in json.loads(Path(dataset).read_text(encoding='utf-8'))['questions']}
    rows = {r['id']: r for r in source['rows']}
    items = []
    for identifier in REVIEW_IDS:
        q, row = questions[identifier], rows[identifier]
        items.append({
            'id': identifier, 'concern': CONCERNS[identifier], 'question': q['question'],
            'expected_answerable': q['answerable'], 'expected_articles': q['expected_articles'],
            'required_facts_unchanged': q['must_include'], 'must_not_include': q['must_not_include'],
            'must_not_cite': q.get('must_not_cite', []),
            'automated_snapshot': {'response': row['response'], 'judge': row['judge'], 'retrieval': row['retrieval']},
            'evidence': row['evidence'], 'evidence_sha256': row['evidence_sha256'],
            'human_review': {'reviewer': None, 'reviewed_at': None, 'verdict': None,
                             'answer_correct': None, 'evidence_sufficient': None,
                             'abstention_appropriate': None, 'wrong_law_attribution': None,
                             'facts': [{'id': i, 'present': None, 'relevant_to_question': None, 'notes': None}
                                       for i in range(len(q['must_include']))],
                             'claim_support_notes': None, 'answer_key_recommendation': None, 'notes': None}})
    worksheet = {'schema_version': 1, 'source_path': str(input_path),
                 'source_sha256': hashlib.sha256(original).hexdigest(),
                 'instructions': 'Fill human_review only; preserve automated_snapshot and original artifacts. Unknown fields stay null. No historical repair or legal correctness inferred from IDs.',
                 'items': items}
    lines = ['# Phase 4.1 manual-review worksheet', '', worksheet['instructions'], '',
             'Exact historical schema errors cannot be reconstructed: rejected response bodies were not retained.',
             'The companion JSON contains all exact evidence excerpts and blank, separate human-review fields.', '']
    for item in items:
        lines += [f"## {item['id']}", '', item['concern'], '', '**Question:** ' + item['question'], '',
                  '**Saved answer (untrusted text):**', '', '```text', item['automated_snapshot']['response']['answer'], '```', '',
                  '**Original automated judgment:**', '', '```json', json.dumps(item['automated_snapshot']['judge'], indent=2, ensure_ascii=False), '```', '',
                  '**Unchanged required facts:**', '']
        lines += [f"- Fact {i}: {fact['fact']}" for i, fact in enumerate(item['required_facts_unchanged'])]
        lines += ['', '**Evidence map** (full exact excerpts in companion JSON):', '']
        lines += [f"- [{e['evidence_id']}] {e['source_document']} / {e['article']}" for e in item['evidence']]
        lines += ['', '**Human review — pending:**', '',
                  '- Reviewer/date:', '- Answer correctness and fact coverage:',
                  '- Claim-to-citation support and applicable employment regime:',
                  '- Evidence sufficiency / appropriateness of abstention:',
                  '- Answer-key relevance / proposed correction (do not edit the dataset):',
                  '- Verdict / rationale:', '']
    write_new_json(output, worksheet)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with markdown_path.open('x', encoding='utf-8') as file:
        file.write('\n'.join(lines))
    return worksheet


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parent / 'data/eval_set.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--markdown', type=Path, required=True)
    args = p.parse_args()
    try:
        result = create_worksheet(args.input, args.dataset, args.output, args.markdown)
    except (ValueError, FileExistsError) as exc:
        p.error(str(exc))
    print(f"Created worksheet for {len(result['items'])} cases; human verdicts pending.")


if __name__ == '__main__':
    main()
