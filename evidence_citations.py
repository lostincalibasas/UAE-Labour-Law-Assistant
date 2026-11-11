"""Resolve query-local evidence references; this does not judge claim support."""

import re

FALLBACK = (
    "I don't have enough information in the available documents "
    "to answer this confidently."
)

_GROUP = re.compile(r"\[([^\[\]\n]*)\]|\(([^()\n]*)\)")
_TOKEN = re.compile(r"\bE\s*\d+\w*\b", re.IGNORECASE)
_ID = re.compile(r"E\s*\d+", re.IGNORECASE)


def build_evidence(chunks):
    """Copy passage metadata, assigning IDs that are valid only for this query."""
    evidence = []
    for rank, chunk in enumerate(chunks, 1):
        text = chunk.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        article = chunk.get("article")
        if not article or str(article).strip().lower() == "unknown":
            article = None
        evidence.append({
            "evidence_id": f"E{rank}",
            "source_document": chunk.get("source_document") or "Unknown source",
            "article": article,
            "filename": chunk.get("filename"),
            "text": text,
        })
    return evidence


def parse_citations(answer):
    """Accept bracketed/parenthesized IDs, comma/semicolon lists and whitespace.

    Ranges, bare IDs and malformed evidence markers are rejected, not guessed.
    Repeated references are returned once, in first-citation order.
    """
    ids, invalid_markers, covered = [], [], []
    for match in _GROUP.finditer(answer):
        content = next(group for group in match.groups() if group is not None)
        if not _TOKEN.search(content):
            continue
        covered.append(match.span())
        parts = re.split(r"[,;]", content)
        if not all(_ID.fullmatch(part.strip()) for part in parts):
            invalid_markers.append(match.group())
            continue
        for part in parts:
            identifier = re.sub(r"\s+", "", part).upper()
            if identifier not in ids:
                ids.append(identifier)
    for match in _TOKEN.finditer(answer):
        if not any(start <= match.start() and match.end() <= end for start, end in covered):
            invalid_markers.append(match.group())
    return ids, list(dict.fromkeys(invalid_markers))


def resolve_answer(answer, evidence):
    """Return only citations resolved from supplied evidence, or a safe fallback.

    A valid ID proves reference identity only. A false claim with a valid ID
    remains semantically unverified and must be evaluated separately.
    """
    answer = (answer or "").strip()
    by_id = {item["evidence_id"]: item for item in evidence}
    ids, invalid_markers = parse_citations(answer)
    invalid_ids = [identifier for identifier in ids if identifier not in by_id]
    if not evidence:
        status = "no_evidence"
    elif not answer or answer.startswith(FALLBACK):
        status = "insufficient_evidence"
    elif invalid_ids or invalid_markers:
        status = "invalid_citations"
    elif not ids:
        status = "missing_citations"
    else:
        status = "valid"

    citations, sources = [], []
    if status == "valid":
        for identifier in ids:
            item = by_id[identifier]
            citations.append({
                "evidence_id": identifier,
                "source_document": item["source_document"],
                "article": item["article"],
                "filename": item["filename"],
                "excerpt": item["text"],
            })
            label = item["source_document"]
            if item["article"]:
                label += f" — {item['article']}"
            if label not in sources:
                sources.append(label)
    return {
        "status": "ok" if status == "valid" else "insufficient_evidence",
        "error": None,
        "answer": answer if status == "valid" else FALLBACK,
        "sources": sources,
        "citations": citations,
        "citation_validation": {
            "status": status,
            "invalid_ids": invalid_ids,
            "invalid_markers": invalid_markers,
        },
        "claim_support": "not_evaluated",
    }
