import chromadb
from sentence_transformers import SentenceTransformer

DB_PATH = "data/chroma_db"

model = SentenceTransformer("all-MiniLM-L6-v2")
client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(name="compliance_docs")

def retrieve_chunks(query, top_k=10):
    query_embedding = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k
    )

    chunks = []
    for i in range(len(results["documents"][0])):
        # chunks.append({
        #     "text": results["documents"][0][i],
        #     "source_document": results["metadatas"][0][i]["source_document"],
        #     "distance": results["distances"][0][i]
        # })
        
        metadata = results["metadatas"][0][i]

        chunks.append({
            "text": results["documents"][0][i],
            "source_document": metadata["source_document"],
            "filename": metadata.get("filename", "unknown"),
            "article": metadata.get("article", "unknown"),
            "distance": results["distances"][0][i]
        })

    return chunks


# if __name__ == "__main__":
#     test_query = "How much notice must an employee give when resigning?"
#     results = retrieve_chunks(test_query, top_k=10)

#     print(f"Query: {test_query}\n")

#     for i, r in enumerate(results):
#         print(
#             f"--- Result {i+1} "
#             f"({r['article']}, "
#             f"from {r['source_document']}, "
#             f"distance: {r['distance']:.4f}) ---"
#         )
#         print(r["text"][:300] + "...\n")


if __name__ == "__main__":
    questions = [
        "I am still on probation and want to resign to join another company in the UAE. How much notice must I give?",
        "I am on probation and want to join another company in the UAE. How much notice should I give?"
    ]

    print("Collection metadata:", collection.metadata)
    print("Collection count:", collection.count())

    for question in questions:
        print(f"\nQUESTION: {question}")

        #results = retrieve_chunks(question, top_k=10)
        results = retrieve_chunks(question, top_k=30)
        for rank, chunk in enumerate(results, start=1):
            print(
                f"{rank}. {chunk['source_document']} | "
                f"{chunk['article']} | "
                f"distance={chunk['distance']:.4f}"
            )
