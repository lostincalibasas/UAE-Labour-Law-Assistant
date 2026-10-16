
import os
import re

from dotenv import load_dotenv
from openai import OpenAI
from retrieve_bge import retrieve_chunks


# Load environment variables
load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

MODEL = "deepseek-chat"

FALLBACK = (
    "I don't have enough information in the available documents "
    "to answer this confidently."
)

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
8. Use clear, professional language and avoid unnecessary repetition.
"""


def generate_answer(query, top_k=10):
    """
    Retrieve relevant legal chunks using BGE and generate
    an answer with DeepSeek using only the retrieved context.
    """

    # Step 1: Retrieve chunks
    chunks = retrieve_chunks(query, top_k=top_k)

    # Step 2: Handle empty retrieval
    if not chunks:
        return {
            "answer": FALLBACK,
            "sources": []
        }

    # Step 3: Build context
    context_parts = []

    for chunk in chunks:
        context_parts.append(
            f"[Source: {chunk['source_document']} | {chunk['article']}]\n"
            f"{chunk['text']}"
        )

    context_text = "\n\n".join(context_parts)

    # Step 4: Prepare user message
    user_message = f"""Context:
{context_text}

Question: {query}

Answer the question using only the context above, and cite the source document(s) you used."""

    # Step 5: Generate answer
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )

    answer = (response.choices[0].message.content or "").strip()

    # Step 6: Identify citations explicitly mentioned in the answer
    sources = []

    for chunk in chunks:
        source = chunk["source_document"]
        article = chunk["article"]

        if source in answer and re.search(
            rf"\b{re.escape(article)}\b(?!\d)", answer
        ):
            citation = f"{source} — {article}"

            if citation not in sources:
                sources.append(citation)

    return {
        "answer": answer,
        "sources": sources
    }


if __name__ == "__main__":
    test_query = "When can an employee resign during probation?"

    result = generate_answer(test_query)

    print(f"Question: {test_query}\n")
    print(f"Answer:\n{result['answer']}\n")
    print(f"Sources: {', '.join(result['sources'])}")
