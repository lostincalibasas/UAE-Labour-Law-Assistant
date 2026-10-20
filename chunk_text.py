
import json
import re
from collections import Counter

from langchain_text_splitters import RecursiveCharacterTextSplitter


INPUT_FILE = "data/extracted_text.json"
OUTPUT_FILE = "data/chunks.json"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Match Article/Addition headings only when they occupy their own line.
# Schedule headings may have a title after the colon.

HEADING_RE = re.compile(
    r"(?im)^[ \t]*(?:"
    r"(?P<kind>article|addition)[ \t]*"
    r"\(?[ \t]*(?P<art>\d+)[ \t]*\)?[ \t]*\**[ \t]*"
    r"|"
    r"schedule[ \t]+no\.?[ \t]*"
    r"\(?[ \t]*(?P<sch>\d+)[ \t]*\)?[ \t]*:"
    r")[ \t]*$"
)
# HEADING_RE = re.compile(
#     r"(?im)^[ \t]*(?:"
#     r"(?P<kind>article|addition)[ \t]*"
#     r"\(?[ \t]*(?P<art>\d+)[ \t]*\)?[ \t]*"
#     r"|"
#     r"schedule[ \t]+no\.?[ \t]*"
#     r"\(?[ \t]*(?P<sch>\d+)[ \t]*\)?[ \t]*:"
#     r")[ \t]*$"
# )

# Repeated headers and disclaimers found in the PDFs.
BOILERPLATE = [
    (
        r"CABINET\s+RESOLUTION\s+NO\.?\s*106\s+OF\s+2022"
        r"\s+PERTAINING\s+TO\s+THE\s+EXECUTIVE\s+REGULATIONS"
        r"\s+OF\s+FEDERAL\s+DECREE\s+LAW\s+NO\.?\s*9\s+OF\s+2022"
        r"\s+CONCERNING\s+DOMESTIC\s+WORKERS"
    ),
    r"THIS\s+IS\s+NOT\s+AN\s+OFFICIAL\s+TRANSLATION",
    (
        r"This\s+document\s+was\s+translated\s+to\s+English"
        r"\s+through\s+a\s+third\s+party\.?\s*"
        r"The\s+ministry\s+is\s+not\s+responsible\s+for\s+any"
        r"\s+possible\s+discrepancies\s+between\s+it\s+and"
        r"\s+the\s+original\s+document"
    ),
]

# The Decree-Law PDF also contains Cabinet Resolution No. 92 of 2022.
# This marker looks for the duplicated resolution heading at the boundary.
EMBEDDED_LAWS = {
    "Federal Decree-Law No. 33 of 2021": {

    "marker": (
        r"Cabinet\s+Resolution\s+No\.?\s*92\s+of\s+2022"
        r"\s*Cabinet\s+Resolution\s+No\.?\s*92\s+of\s+2022"
    ),
        "title": "Cabinet Resolution No. 92 of 2022",
    }
}


def clean_text(text):
    """Remove known repeated PDF boilerplate and normalize whitespace."""
    for pattern in BOILERPLATE:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    text = text.replace("\t", " ")

    # Remove standalone PDF page numbers.
    text = re.sub(r"(?m)^[ \t]*\d{1,3}[ \t]*$", "", text)

    # Remove trailing spaces and excessive blank lines.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_embedded(doc_title, text):
    """Separate an embedded law when its boundary marker is found."""
    config = EMBEDDED_LAWS.get(doc_title)

    if not config:
        return [(doc_title, text)]

    matches = list(
        re.finditer(config["marker"], text, flags=re.IGNORECASE)
    )

    if not matches:
        print(
            f"WARNING: Could not find the boundary for "
            f"{config['title']} inside {doc_title}. "
            "Keeping the original document together."
        )
        return [(doc_title, text)]

    # Use the last duplicated heading marker as the boundary.
    cut = matches[-1].start()

    first_law = text[:cut].strip()
    second_law = text[cut:].strip()

    if not first_law or not second_law:
        print(
            f"WARNING: Invalid split for {config['title']}. "
            "Keeping the original document together."
        )
        return [(doc_title, text)]

    return [
        (doc_title, first_law),
        (config["title"], second_law),
    ]


def pick_title(body):
    """Extract a likely article title from the first non-empty line."""
    for line in body.splitlines():
        line = line.strip()

        if not line:
            continue

        looks_like_title = (
            len(line) <= 80
            and not line.endswith((".", ",", ";", ":"))
            and not re.search(r"\bshall\b", line, flags=re.IGNORECASE)
        )

        return line if looks_like_title else ""

    return ""


def build_chunks(law_title, filename, text, splitter):
    """Split a law at detected headings, then chunk oversized articles."""
    chunks = []
    matches = list(HEADING_RE.finditer(text))

    if not matches:
        print(f"WARNING: No article headings found in {law_title}")
        return chunks

    # Text before the first detected heading is skipped.
    # This usually includes the cover page and table of contents.
    
    last_number = 0
    for i, match in enumerate(matches):
        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )
        body = text[match.end():end].strip()

        if match.group("art"):
            number = int(match.group("art"))

            # Correct the duplicate Article 17 label in this specific law.
            if (
                law_title == "Federal Decree-Law No. 9 of 2022"
                and number == 17
                and last_number == 26
                and any(
                    int(m.group("art")) == 28
                    for m in matches[i + 1:]
                    if m.group("art")
                )
            ):
                number = 27

            if number <= last_number:
                print(
                    f"WARNING: Article {number} appears after "
                    f"Article {last_number} in {law_title}. "
                    "Check the source text and heading detection."
                )

            last_number = max(last_number, number)
            label = f"Article {number}"
            title = pick_title(body)

        else:
            label = f"Schedule {match.group('sch')}"
            title = ""

        header = f"{law_title} | {label}"
        if title:
            header += f" | {title}"

        # Keep small articles together; split only oversized articles.
        pieces = (
            splitter.split_text(body)
            if len(body) > CHUNK_SIZE
            else [body]
        )

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue

            chunks.append({
                "text": f"{header}\n{piece}",
                "source_document": law_title,
                "filename": filename,
                "article": label,
            })
    return chunks



def chunk_documents():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        documents = json.load(f)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks = []

    for doc in documents:
        print(f"Processing {doc['title']}")

        text = clean_text(doc["text"])

        for law_title, law_text in split_embedded(
            doc["title"], text
        ):
            all_chunks.extend(
                build_chunks(
                    law_title,
                    doc["filename"],
                    law_text,
                    splitter,
                )
            )

    # Assign stable, sequential IDs for this generated chunk file.
    all_chunks = [
        {"chunk_id": i, **chunk}
        for i, chunk in enumerate(all_chunks)
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(
        f"\nDone. Created {len(all_chunks)} chunks "
        f"from {len(documents)} input files."
    )

    print("\nChunks by source document:")
    for name, count in sorted(
        Counter(c["source_document"] for c in all_chunks).items()
    ):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    chunk_documents()