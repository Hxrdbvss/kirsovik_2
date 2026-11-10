from pathlib import Path
import re

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent
PDF_PATH = PROJECT_DIR / "documents" / "lab_manual.pdf"
DB_PATH = PROJECT_DIR / "manual_chroma_db"
COLLECTION_NAME = "lab_manual"

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

CHUNK_SIZE = 1000
OVERLAP = 200


def split_text(text):
    """Разделяет текст страницы на фрагменты с перекрытием."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))

        if end < len(text):
            boundary = text.rfind(" ", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(start + 1, end - OVERLAP)

    return chunks


if not PDF_PATH.is_file():
    raise FileNotFoundError(f"Документ не найден: {PDF_PATH}")

reader = PdfReader(PDF_PATH)

documents = []
ids = []
metadatas = []
empty_pages = []

for page_index, page in enumerate(reader.pages):
    page_number = page_index + 1
    text = page.extract_text() or ""
    chunks = split_text(text)

    if not chunks:
        empty_pages.append(page_number)

    for chunk_index, chunk in enumerate(chunks, start=1):
        ids.append(f"page_{page_number:03d}_chunk_{chunk_index:03d}")
        documents.append(chunk)
        metadatas.append({
            "source": PDF_PATH.name,
            "page": page_number,
            "chunk": chunk_index,
        })

if not documents:
    raise RuntimeError("Не удалось извлечь текст ни с одной страницы.")

print(f"Страниц в документе: {len(reader.pages)}")
print(f"Страниц без извлечённого текста: {len(empty_pages)}")
if empty_pages:
    print("Их номера:", empty_pages)

print(f"Подготовлено фрагментов: {len(documents)}")
print("Загрузка модели эмбеддингов на CPU...")

embedder = SentenceTransformer(MODEL_NAME, device="cpu")

print("Создание эмбеддингов...")
embeddings = embedder.encode(
    documents,
    batch_size=32,
    show_progress_bar=True,
    convert_to_numpy=True,
).tolist()

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)

# Одинаковые ID обновляются при повторном запуске.
batch_size = 100
for start in range(0, len(ids), batch_size):
    end = start + batch_size
    collection.upsert(
        ids=ids[start:end],
        documents=documents[start:end],
        metadatas=metadatas[start:end],
        embeddings=embeddings[start:end],
    )

print("\nИндексация завершена.")
print("Путь к базе:", DB_PATH)
print("Коллекция:", COLLECTION_NAME)
print("Фрагментов в коллекции:", collection.count())
