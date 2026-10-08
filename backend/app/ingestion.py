from pathlib import Path
import re
import hashlib
import fitz
from sentence_transformers import SentenceTransformer
import chromadb
from .config import DATA_DIR, CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP

def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_text(text: str, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks

def extract_pdf(pdf_path: Path):
    doc = fitz.open(pdf_path)
    records = []
    try:
        for page_num, page in enumerate(doc, start=1):
            text = clean_text(page.get_text("text"))
            if not text:
                continue
            for chunk_index, chunk in enumerate(split_text(text)):
                records.append({
                    "text": chunk,
                    "source_doc": pdf_path.name,
                    "page_number": page_num,
                    "section_heading": None,
                    "chunk_index": chunk_index,
                })
    finally:
        doc.close()
    return records

def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

def ingest(force=False):
    model = SentenceTransformer(EMBEDDING_MODEL)
    collection = get_collection()

    if force and collection.count():
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {DATA_DIR}")

    total = 0
    for pdf in pdfs:
        records = extract_pdf(pdf)
        if not records:
            print(f"WARNING: no extractable text in {pdf.name}")
            continue

        texts = [r["text"] for r in records]
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()
        ids, metas = [], []

        for i, r in enumerate(records):
            raw = f'{r["source_doc"]}|{r["page_number"]}|{r["chunk_index"]}|{r["text"][:80]}'
            ids.append(hashlib.sha1(raw.encode("utf-8")).hexdigest())
            metas.append({
                "source_doc": r["source_doc"],
                "page_number": r["page_number"],
                "section_heading": r["section_heading"] or "",
                "chunk_index": r["chunk_index"],
            })

        collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metas,
            embeddings=embeddings
        )
        total += len(records)
        print(f"Ingested {pdf.name}: {len(records)} chunks")

    print(f"Total chunks indexed: {total}")
    return total

if __name__ == "__main__":
    ingest(force=True)
