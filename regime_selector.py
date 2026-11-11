"""Experimental question-only selector. Not used by production retrieval.

The catalog is reviewed corpus metadata, not an evaluation answer key. Ambiguity
means no filter, not a guessed regime or an answer abstention.
"""
import re
import unicodedata

GENERAL = 'Federal Decree-Law No. 33 of 2021'
DOMESTIC = ('Federal Decree-Law No. 9 of 2022', 'Cabinet Decision No. 106 of 2022',
            'Cabinet Resolution No. 92 of 2022')
CATALOG = {GENERAL: 'general', **{name: 'domestic' for name in DOMESTIC}}
VERSION = 'phase42-v1'


def select_regime(question, source_documents):
    """Only question text and available source names are accepted as inputs.

    The returned where clause is built from exact catalog names, never from user
    text. No labels, expected articles, IDs, distances or answer facts are used.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError('A nonempty question is required')
    sources = set(source_documents)
    if not sources or not all(isinstance(s, str) for s in sources):
        raise ValueError('Nonempty source document metadata is required')
    text = unicodedata.normalize('NFKC', question).casefold()
    text = re.sub(r'[\u2010-\u2015]', '-', text)
    general = bool(re.search(r'\bprivate[ -]sector\b|\b(?:main|general) (?:uae )?labou?r law\b|\b(?:decree[ -])?law\s*(?:no\.?\s*)?\(?33\)?\s*(?:of\s*)?2021\b', text))
    domestic = bool(re.search(r'\bdomestic[ -](?:workers?|employees?|helpers?|servants?)\b|\bhousehold (?:workers?|employees?|staff)\b|\b(?:decree[ -])?law\s*(?:no\.?\s*)?\(?9\)?\s*(?:of\s*)?2022\b|\bcabinet (?:decision|resolution)\s*(?:no\.?\s*)?\(?(?:106|92)\)?\s*(?:of\s*)?2022\b', text))
    def decision(status, reason, regime=None):
        selected = sorted(s for s in sources if CATALOG.get(s) == regime) if regime else []
        if regime and not selected:
            return decision('uncertain', 'requested_regime_not_in_catalog')
        return {'version': VERSION, 'status': status, 'reason': reason,
                'signals': {'general': general, 'domestic': domestic},
                'regime': regime, 'sources': selected,
                'where': {'source_document': {'$in': selected}} if selected else None}
    if sources - CATALOG.keys():
        return decision('uncertain', 'unmapped_source_metadata')
    if re.search(r'\b(ignore|override|pretend)\b|\bsystem\s*:|\b(?:force|select|route|filter|classify)\b.{0,40}\b(regime|law|domestic|general)\b', text):
        return decision('uncertain', 'routing_instruction_or_untrusted_context')
    if re.search(r'\b(difc|adgm|government|civil service|military|police|saudi|qatar|oman|bahrain|kuwait|india|uk|british)\b', text):
        return decision('uncertain', 'outside_or_unclear_jurisdiction')
    if re.search(r'\b(not sure|unsure|uncertain|unknown|maybe|perhaps|possibly|which law|which regime|whether i|whether the|may be classified|either)\b', text):
        return decision('uncertain', 'uncertain_employment_context')
    if re.search(r'\b(not|isn.t|aren.t|excluding|except|formerly|previously|rather than|instead of|no longer)\b.{0,50}\b(domestic|household|private|general|main)\b', text):
        return decision('uncertain', 'negated_or_changed_employment_context')
    if re.search(r'\b(domestic workers?|household workers?|private[ -]sector employees?)\b.{0,15}\b(?:are|is) not (?:the topic|my (?:role|job|status))\b', text):
        return decision('uncertain', 'negated_employment_subject')
    if ('"' in text or '\u201c' in text or '\u201d' in text) and (general or domestic):
        return decision('uncertain', 'quoted_regime_context')
    if general and domestic:
        return decision('mixed', 'multiple_regimes_mentioned')
    if general:
        return decision('filtered', 'explicit_general_regime', 'general')
    if domestic:
        return decision('filtered', 'explicit_domestic_regime', 'domestic')
    return decision('uncertain', 'no_unambiguous_regime_signal')
