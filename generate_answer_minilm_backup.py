import os
import re
from dotenv import load_dotenv
from openai import OpenAI
from retrieve import retrieve_chunks

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# SYSTEM_PROMPT = """You are a compliance assistant answering questions about UAE labor law.

# Rules you must follow:
# 1. Only answer using the provided context below. Never use outside knowledge.
# 2. Always cite which source document each piece of information comes from.
# 3. If the context does not contain enough information to answer, respond exactly with:
#    "I don't have enough information in the available documents to answer this confidently."
# 4. Do not guess or extrapolate beyond what the context states."""

SYSTEM_PROMPT = """You are a compliance assistant answering questions about UAE labor law.

Rules you must follow:

1. Answer only using the provided context. Never use outside knowledge.
2. Answer the user's specific question directly and concisely. Do not include unrelated legal rules or extra scenarios unless the user asks for them.
3. Use the most relevant context to answer the question. Do not combine different legal topics simply because they appear in the retrieved context.
4. Cite the source document and article number for each legal rule you explain, when that information is available in the context.
5. Distinguish between general employment rules and rules that apply only to specific situations, such as probation or domestic workers. Do not mix these rules unless the question requires it.
6. If the context does not contain enough information to answer confidently, respond exactly with:
   "I don't have enough information in the available documents to answer this confidently."
7. Do not guess, invent citations, or extrapolate beyond what the context states.
8. Use clear, professional language and avoid unnecessary repetition."""


DISTANCE_THRESHOLD = 1.2  # chunks with distance above this are considered not relevant enough

def generate_answer(query, top_k=10):
  
  
    chunks = retrieve_chunks(query, top_k=top_k)

    print("\n--- DEBUG: Retrieved chunks ---")
    for i, chunk in enumerate(chunks):
        print(
            f"Rank {i + 1} | "
            f"Distance: {chunk['distance']:.4f} | "
            f"Article: {chunk.get('article', 'unknown')} | "
            f"Text: {chunk['text'][:150]!r}"
        )

    relevant_chunks = [
        c for c in chunks
        if c["distance"] <= DISTANCE_THRESHOLD
    ]

    print(f"\nDistance threshold: {DISTANCE_THRESHOLD}")
    print(f"Chunks retrieved: {len(chunks)}")
    print(f"Chunks passing threshold: {len(relevant_chunks)}")

    if not relevant_chunks:
        return {
            "answer": "I don't have enough information in the available documents to answer this confidently.",
            "sources":[]
        }
    
    context_text = ""
    for chunk in relevant_chunks:
        context_text += (
            f"\n[Source: {chunk['source_document']} | "
            f"{chunk['article']}]\n"
            f"{chunk['text']}\n"
        )


    user_message = f"""Context:
{context_text}

Question: {query}

Answer the question using only the context above, and cite the source document(s) you used."""

    MODEL = "deepseek-chat"
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )

    answer = response.choices[0].message.content
    
    sources = []

    for chunk in relevant_chunks:
        source = chunk["source_document"]
        article = chunk["article"]

        # Show only articles explicitly mentioned in the answer.
        
        if source in answer and re.search(
            rf"\b{re.escape(article)}\b(?!\d)", answer
        ):
            citation = f"{source} — {article}"

            if citation not in sources:
                sources.append(citation)

    return {"answer": answer, "sources": sources}

if __name__ == "__main__":
    test_query = "When can an employee resign during probation?"
    #test_query = "What are the rules for soccer players?"
    result = generate_answer(test_query)

    print(f"Question: {test_query}\n")
    print(f"Answer:\n{result['answer']}\n")
    print(f"Sources: {', '.join(result['sources'])}")
   