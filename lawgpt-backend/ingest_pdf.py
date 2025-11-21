import pdfplumber
import re
import os
from google.cloud import firestore

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "genial-smoke-478804-t1")
COLLECTION = "acts"
PDF_DIR = "pdfs"

db = firestore.Client(project=PROJECT_ID)


def extract_keywords(text: str):
    words = re.findall(r"[A-Za-z]+", text.lower())
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "have", "has",
        "shall", "will", "been", "were", "was", "are", "your", "you", "hereby", "such",
        "any", "other", "their", "thereof", "law", "section", "article", "acts",
    }
    filtered = [w for w in words if w not in stop and len(w) > 3]
    return list(dict.fromkeys(filtered))[:10]


def infer_act_name(filename: str) -> str:
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)
    # Remove common suffixes like 'bare act', 'pdf', etc.
    cleaned = re.sub(r"(?i)(bare act|copy|pdf)", "", name)
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or name


def ingest_act_pdf(pdf_path: str, act_name: str | None = None):
    act_name = act_name or infer_act_name(pdf_path)
    print(f"Ingesting: {pdf_path} ({act_name})")
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            doc = {
                "type": "act",
                "act_name": act_name,
                "page_no": i + 1,
                "title": f"{act_name} - Page {i + 1}",
                "text": text,
                "keywords": extract_keywords(text),
            }
            db.collection(COLLECTION).add(doc)
            print("Saved page:", i + 1)


def ingest_all_pdfs(pdf_dir: str = PDF_DIR):
    if not os.path.isdir(pdf_dir):
        raise SystemExit(f"PDF directory not found: {pdf_dir}")

    for filename in os.listdir(pdf_dir):
        if not filename.lower().endswith(".pdf"):
            continue
        pdf_path = os.path.join(pdf_dir, filename)
        ingest_act_pdf(pdf_path)


if __name__ == "__main__":
    ingest_all_pdfs()
