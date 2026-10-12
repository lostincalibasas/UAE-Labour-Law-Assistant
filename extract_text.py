import os
from pypdf import PdfReader
import json

RAW_DOCS_DIR = "data/raw_docs"
OUTPUT_FILE = "data/extracted_text.json"

def extract_all_pdfs():
    documents = []

    for filename in os.listdir(RAW_DOCS_DIR):
        if filename.endswith(".pdf"):
            filepath = os.path.join(RAW_DOCS_DIR, filename)
            print(f"Extracting: {filename}")

            reader = PdfReader(filepath)
            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            documents.append({
                "filename": filename,
                "title": filename.replace(".pdf", "").replace("_", " "),
                "text": full_text
            })

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Extracted {len(documents)} documents to {OUTPUT_FILE}")

if __name__ == "__main__":
    extract_all_pdfs()