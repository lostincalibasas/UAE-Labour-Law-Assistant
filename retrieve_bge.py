"""BGE retriever using the already-built compliance_bge ChromaDB collection.

Does not create or alter logical collection contents. Chroma's persistent read
operations may still write physical storage; use verify_index.py for safe tests.
"""

from pathlib import Path

from rag_errors import RAGError
from index_paths import resolve_index_path

DB_PATH = Path(__file__).resolve().parent / "data" / "chroma_db"
COLLECTION_NAME = "compliance_bge"
MODEL_NAME = "BAAI/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

model = None
client = None
client_path = None


def get_collection():
    global client, client_path
    path = resolve_index_path(DB_PATH)
    if client is not None and client_path != path:
        # Closing a stale client may write its index. Refuse instead of switching.
        raise RAGError("index_isolation", "retrieval")
    # PersistentClient can create a database: refuse missing storage first.
    if not (path / "chroma.sqlite3").is_file():
        raise RAGError("index_missing", "retrieval")
    try:
        import chromadb
        from chromadb.config import Settings
        from chromadb.errors import NotFoundError
    except ImportError:
        raise RAGError("dependency_unavailable", "retrieval") from None
    try:
        if client is None:
            client = chromadb.PersistentClient(
                path=str(path),
                settings=Settings(migrations="validate", anonymized_telemetry=False),
            )
            client_path = path
        return client.get_collection(name=COLLECTION_NAME)
    except NotFoundError:
        raise RAGError("collection_missing", "retrieval") from None
    except Exception:
        client = None
        raise RAGError("retrieval_unavailable", "retrieval") from None


def get_model():
    global model
    if model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(MODEL_NAME)
        except Exception:
            raise RAGError("embedding_unavailable", "retrieval") from None
    return model


def retrieve_chunks(query, top_k=10):
    """Return chunks in BGE cosine-distance order (smaller distance is better)."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer")

    try:
        collection = get_collection()
        count = collection.count()
        if not isinstance(count, int) or count < 0:
            raise RAGError("retrieval_invalid", "retrieval")
        if count == 0:
            raise RAGError("collection_empty", "retrieval")
    except RAGError:
        raise
    except Exception:
        raise RAGError("retrieval_unavailable", "retrieval") from None
    try:
        query_embedding = get_model().encode(
            QUERY_PREFIX + query, normalize_embeddings=True,
        ).tolist()
    except RAGError:
        raise
    except Exception:
        raise RAGError("embedding_unavailable", "retrieval") from None
    try:
        results = collection.query(
            query_embeddings=[query_embedding], n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        raise RAGError("retrieval_unavailable", "retrieval") from None

    try:
        documents, metadatas, distances = (
            results[key][0] for key in ("documents", "metadatas", "distances")
        )
        if not (len(documents) == len(metadatas) == len(distances)):
            raise ValueError("Inconsistent retrieval result")
        chunks = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            if (not isinstance(document, str) or not document.strip()
                    or not isinstance(metadata.get("source_document"), str)
                    or not metadata["source_document"].strip()):
                raise ValueError("Invalid passage")
            chunks.append({
                "text": document,
                "source_document": metadata["source_document"],
                "filename": metadata.get("filename", "unknown"),
                "article": metadata.get("article", "unknown"),
                "distance": float(distance),
            })
    except Exception:
        raise RAGError("retrieval_invalid", "retrieval") from None
    return chunks


if __name__ == "__main__":
    questions = [
        "I am on probation and want to join another company in the UAE. How much notice should I give?",
        "How much notice must an employee give when resigning?",
    ]
    print(f"Collection: {COLLECTION_NAME}")
    for question in questions:
        print(f"\nQuestion: {question}")
        for rank, chunk in enumerate(retrieve_chunks(question, top_k=5), 1):
            print(f"  {rank}. {chunk['source_document']} | {chunk['article']} | cosine distance={chunk['distance']:.4f}")
