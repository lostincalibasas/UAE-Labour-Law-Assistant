"""Deterministic logical fingerprints, independent of HNSW/SQLite file layout."""

import hashlib
import json
import math
import struct


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def collection_fingerprint(collection):
    count = collection.count()
    records = {}
    for offset in range(0, count, 256):
        batch = collection.get(limit=256, offset=offset,
                               include=["documents", "metadatas", "embeddings"])
        for pos, identifier in enumerate(batch["ids"]):
            if identifier in records:
                raise ValueError("Duplicate stored chunk ID")
            vector = [float(value) for value in batch["embeddings"][pos]]
            if not vector or not all(math.isfinite(value) for value in vector):
                raise ValueError("Missing or non-finite stored embedding")
            records[identifier] = {
                "document": digest(batch["documents"][pos]),
                "metadata": digest(batch["metadatas"][pos]),
                "dimension": len(vector),
                # Exact returned values, canonical little-endian float64, no rounding.
                "embedding": hashlib.sha256(struct.pack(f"<{len(vector)}d", *vector)).hexdigest(),
            }
    if len(records) != count or collection.count() != count:
        raise ValueError("Collection changed while reading logical contents")
    records = dict(sorted(records.items()))
    return {"count": count, "ids_sha256": digest(list(records)),
            "dimensions": sorted({r["dimension"] for r in records.values()}),
            "collection_metadata_sha256": digest(collection.metadata),
            "documents_sha256": digest([(k, r["document"]) for k, r in records.items()]),
            "metadatas_sha256": digest([(k, r["metadata"]) for k, r in records.items()]),
            "embeddings_sha256": digest([(k, r["dimension"], r["embedding"]) for k, r in records.items()]),
            "records": records}


def index_fingerprint(client):
    names = sorted(getattr(c, "name", c) for c in client.list_collections())
    return {name: collection_fingerprint(client.get_collection(name)) for name in names}


def logical_differences(left, right):
    differences = {}
    for name in sorted(set(left) | set(right)):
        if name not in left or name not in right:
            differences[name] = {"collection_presence": "different"}
            continue
        a, b = left[name], right[name]
        fields = [key for key in a if key != "records" and a[key] != b.get(key)]
        ids = sorted(key for key in set(a["records"]) | set(b["records"])
                     if a["records"].get(key) != b["records"].get(key))
        if fields or ids:
            differences[name] = {"fields": fields, "changed_ids": ids}
    return differences
