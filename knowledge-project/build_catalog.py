import csv
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_DIR / "graph-db-lab" / "learning_materials.csv"
DB_PATH = PROJECT_DIR / "knowledge-project" / "chroma_db"

COLLECTION_NAME = "learning_catalog"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

if not CSV_PATH.is_file():
    raise SystemExit(f"Файл не найден: {CSV_PATH}")

with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)
    required = {"id", "title", "topic", "level"}

    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise SystemExit(f"В CSV нужны столбцы: {', '.join(sorted(required))}")

    rows = list(reader)

if not rows:
    raise SystemExit("Каталог пуст.")

for row in rows:
    if any(not (row.get(key) or "").strip() for key in required):
        raise SystemExit(f"Обнаружена запись с пустым обязательным полем: {row}")

ids = [row["id"].strip() for row in rows]

if len(ids) != len(set(ids)):
    raise SystemExit("В CSV найдены повторяющиеся id.")

documents = [
    (
        f"Название: {row['title'].strip()}. "
        f"Тема: {row['topic'].strip()}. "
        f"Уровень: {row['level'].strip()}."
    )
    for row in rows
]

metadata = [
    {
        "title": row["title"].strip(),
        "topic": row["topic"].strip(),
        "level": row["level"].strip(),
        "source": str(CSV_PATH),
    }
    for row in rows
]

print("Загрузка модели эмбеддингов на CPU...", flush=True)
embedder = SentenceTransformer(MODEL_NAME, device="cpu")
embeddings = embedder.encode(
    documents,
    convert_to_numpy=True,
).tolist()

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# Повторный запуск обновляет записи с теми же id.
collection.upsert(
    ids=ids,
    documents=documents,
    metadatas=metadata,
    embeddings=embeddings,
)

print(f"Загружено записей из CSV: {len(rows)}")
print(f"Всего записей в коллекции: {collection.count()}")
print(f"Путь к базе: {DB_PATH}")
print(f"Коллекция: {COLLECTION_NAME}")
