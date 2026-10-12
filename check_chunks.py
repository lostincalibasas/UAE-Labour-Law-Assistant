
import json
from collections import defaultdict

CHUNKS_FILE = "data/chunks.json"

expected = {
    "Federal Decree-Law No. 33 of 2021": 74,
    "Cabinet Resolution No. 92 of 2022": 12,
    "Federal Decree-Law No. 9 of 2022": 32,
    "Cabinet Decision No. 106 of 2022": 20,
}

with open(CHUNKS_FILE, encoding="utf-8") as f:
    chunks = json.load(f)

found = defaultdict(set)
chunk_counts = defaultdict(int)
empty_chunks = []

for chunk in chunks:
    source = chunk["source_document"]
    article = chunk["article"]
    text = chunk.get("text", "").strip()

    chunk_counts[source] += 1

    if article.startswith("Article "):
        try:
            number = int(article.split()[1])
            found[source].add(number)
        except (ValueError, IndexError):
            print(f"WARNING: Invalid article label: {article!r}")

    # Each chunk should contain a header and a non-empty body.
    body = text.split("\n", 1)[1].strip() if "\n" in text else ""
    if not body:
        empty_chunks.append(chunk.get("chunk_id", "?"))

print("CHUNKS BY SOURCE")
for source, count in sorted(chunk_counts.items()):
    print(f"  {source}: {count}")

print("\nARTICLE COVERAGE")
for law, total in expected.items():
    numbers = found[law]
    missing = sorted(set(range(1, total + 1)) - numbers)

    if missing:
        print(
            f"WARNING: {law}: {len(numbers)}/{total} article numbers found; "
            f"missing {missing}"
        )
    else:
        print(f"OK: {law}: {len(numbers)}/{total} article numbers found")

print("\nEMPTY CHUNKS")
if empty_chunks:
    print(f"WARNING: {len(empty_chunks)} chunks have no body: {empty_chunks}")
else:
    print("None")

print(f"\nTotal chunks checked: {len(chunks)}")