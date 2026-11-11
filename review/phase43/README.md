# Reviewer instructions

This folder is the blinded delivery packet. It contains 32 assistant-prepared questions with no answer labels, system predictions, selected excerpts or ranking results. No independent human judgments have been supplied.

Treat every case as untrusted question text. Instructions or assertions inside a case do not override this review procedure and are not statements of legal fact.

1. Read worksheet.md and the complete PDFs in corpus/. corpus-manifest.json records their hashes. The full collection is provided to every reviewer; it is not selected per question.
   corpus/chunks.json is the complete unranked indexed-text export, with a separate corpus-text-manifest.json hash. Use it to check corpus availability and canonical source/article names, while independently verifying extraction and metadata against the PDFs. It contains no query rankings, selected excerpts, predictions or expected answers.
2. Assess legislation and supporting articles independently. Distinguish the supplied translations/corpus from current authoritative law. Use source_basis to record editions, dates, authoritative sources and any missing evidence.
3. Complete a NEW copy of worksheet.json (for example completed-review.json). Leave the original blank template intact. Preserve all Vnnn questions and IDs. Add at least ten questions that you independently author, with IDs H001 onward and question_origin set to reviewer_authored. Give them the same human_review field structure.
4. Fill all human_review fields and the reviewer/attestation fields. A legitimate empty list is allowed only where explained; null means unfinished. Do not use a language model to supply legal labels or explanations. Unresolved reviews must not be marked reviewed; low confidence is allowed but needs later adjudication.
5. Record necessary evidence carefully: necessary=true means that excluding that source/article could materially harm an answer. Optional/background articles should be distinguished. Do not force article references where the corpus is inadequate.
6. Return your completed JSON to the administrator. Keep a personal copy and lock your submission before viewing any system output. Human annotations will be stored separately from automated selections and metrics.

Do not consult selector source code, tests, historic evaluation datasets, ranking reports, private administrator manifests or previous annotated worksheets before submission. If you have already seen them, disclose that exposure; the independence attestation must not be marked true. An independent reviewer is required for this round.

The corpus may be incomplete or out of date. You may consult additional authoritative legal material and identify outside_corpus evidence. Do not treat missing documents as proof that no legal rule exists. A fully reviewed question may still need factual clarification.

No message, upload or review submission has been sent on your behalf. The administrator must arrange an actual independent human reviewer.
