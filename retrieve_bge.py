"""BGE retriever using the already-built compliance_bge ChromaDB collection.

Run from the compliance-rag project root. Does not create or alter collections.
"""

import chromadb
from sentence_transformers import SentenceTransformer

DB_PATH = "data/chroma_db"
COLLECTION_NAME = "compliance_bge"
MODEL_NAME = "BAAI/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

model = SentenceTransformer(MODEL_NAME)
client = chromadb.PersistentClient(path=DB_PATH)
# Deliberately use get_collection, not get_or_create_collection:
# fail clearly if the benchmark index has not been built.
collection = client.get_collection(name=COLLECTION_NAME)


def retrieve_chunks(query, top_k=10):
    """Return chunks in BGE cosine-distance order (smaller distance is better)."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")

    query_embedding = model.encode(
        QUERY_PREFIX + query,
        normalize_embeddings=True,
    ).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for document, metadata, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": document,
            "source_document": metadata["source_document"],
            "filename": metadata.get("filename", "unknown"),
            "article": metadata.get("article", "unknown"),
            "distance": float(distance),
        })
    return chunks


if __name__ == "__main__":
    questions = [
        "I am on probation and want to join another company in the UAE. How much notice should I give?",
        "How much notice must an employee give when resigning?",
    ]
    print(f"Collection: {COLLECTION_NAME} ({collection.count()} chunks)")
    for question in questions:
        print(f"\nQuestion: {question}")
        for rank, chunk in enumerate(retrieve_chunks(question, top_k=5), 1):
            print(f"  {rank}. {chunk['source_document']} | {chunk['article']} | cosine distance={chunk['distance']:.4f}")
