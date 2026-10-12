"""Build the BGE ChromaDB index used by retrieve_bge.py.

From the project root:
    python build_vector_store_bge.py

If compliance_bge already exists, it is left unchanged. To intentionally
replace it after changing chunks/model, use --rebuild (back up first).
"""

import argparse
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
CHUNKS_FILE = BASE_DIR / "data" / "chunks.json"
DB_PATH = BASE_DIR / "data" / "chroma_db"
COLLECTION_NAME = "compliance_bge"
MODEL_NAME = "BAAI/bge-base-en-v1.5"


def build_vector_store(rebuild=False):
    with CHUNKS_FILE.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    if not isinstance(chunks, list) or not chunks:
        raise ValueError("data/chunks.json must be a non-empty list. Run chunk_text.py first.")

    ids = [str(chunk["chunk_id"]) for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk IDs found")

    for chunk in chunks:
        for field in ("text", "source_document", "filename", "article"):
            if not chunk.get(field):
                raise ValueError(f"Missing {field} for chunk {chunk['chunk_id']}")

    client = chromadb.PersistentClient(path=str(DB_PATH))
    existing = {getattr(item, "name", item) for item in client.list_collections()}

    if COLLECTION_NAME in existing and not rebuild:
        collection = client.get_collection(COLLECTION_NAME)
        print(f"Existing {COLLECTION_NAME}: {collection.count()} chunks. Nothing changed.")
        print("Use --rebuild only when you intentionally want to replace this index.")
        return

    print(f"Loading {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    texts = [chunk["text"] for chunk in chunks]
    print(f"Embedding {len(texts)} chunks...")
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).tolist()

    metadatas = [
        {
            "source_document": chunk["source_document"],
            "filename": chunk["filename"],
            "article": chunk["article"],
        }
        for chunk in chunks
    ]

    # No deletion occurs until the embeddings have been computed successfully.
    # --rebuild replaces the BGE collection only, never compliance_docs (MiniLM).
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        print(f"Replaced old {COLLECTION_NAME} collection")

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    count = collection.count()
    if count != len(chunks):
        raise RuntimeError(f"Index count mismatch: expected {len(chunks)}, got {count}")
    print(f"Verified: {count} chunks in {COLLECTION_NAME} at {DB_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the BGE vector index")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Replace existing compliance_bge collection (destructive; back up first)",
    )
    args = parser.parse_args()
    build_vector_store(rebuild=args.rebuild)
