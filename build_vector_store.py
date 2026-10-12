
import json
import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = "data/chunks.json"
DB_PATH = "data/chroma_db"
COLLECTION_NAME = "compliance_docs"


def build_vector_store():
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    if not chunks:
        raise ValueError("No chunks found in chunks.json")

    texts = [chunk["text"] for chunk in chunks]
    ids = [str(chunk["chunk_id"]) for chunk in chunks]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk IDs found")

    metadatas = [
        {
            "source_document": chunk["source_document"],
            "filename": chunk["filename"],
            "article": chunk["article"]
        }
        for chunk in chunks
    ]

    print("Loading embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"Embedding {len(texts)} chunks...")
    embeddings = model.encode(
        texts,
        show_progress_bar=True
    ).tolist()

    client = chromadb.PersistentClient(path=DB_PATH)

    # Replace the previous collection after embeddings are ready.
    existing_names = [
        collection.name if hasattr(collection, "name") else collection
        for collection in client.list_collections()
    ]

    if COLLECTION_NAME in existing_names:
        client.delete_collection(COLLECTION_NAME)
        print("Deleted old collection")

    collection = client.create_collection(name=COLLECTION_NAME)

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )

    stored_count = collection.count()

    if stored_count != len(chunks):
        raise RuntimeError(
            f"Chunk count mismatch: expected {len(chunks)}, "
            f"stored {stored_count}"
        )

    print(f"Verified: {stored_count} chunks in Chroma")
    print(f"Database location: {DB_PATH}")


if __name__ == "__main__":
    build_vector_store()
