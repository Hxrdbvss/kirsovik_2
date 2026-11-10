from pathlib import Path

import chromadb
import torch
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "vector-db-lab" / "chroma_db"

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)
COLLECTION_NAME = "learning_materials_ru"

if not DB_PATH.is_dir():
    raise FileNotFoundError(
        f"Папка базы ChromaDB не найдена: {DB_PATH}"
    )

client = chromadb.PersistentClient(path=str(DB_PATH))

# Открываем существующую коллекцию, не создавая новую.
collection = client.get_collection(name=COLLECTION_NAME)

if collection.count() == 0:
    raise RuntimeError("Коллекция существует, но не содержит документов.")

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Устройство:", device)
print("Документов в коллекции:", collection.count())
print("Загрузка модели эмбеддингов...")

model = SentenceTransformer(MODEL_NAME, device=device)

def search(question, n_results=3):
    query_embedding = model.encode(
        [question],
        convert_to_numpy=True,
    ).tolist()

    result = collection.query(
        query_embeddings=query_embedding,
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    print(f"\nВопрос: {question}")

    for i, (doc_id, document, metadata, distance) in enumerate(
        zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ),
        start=1,
    ):
        print(f"\n{i}. ID: {doc_id}")
        print(f"   Текст: {document}")
        print(f"   Категория: {metadata.get('category', 'не указана')}")
        print(f"   Расстояние: {distance:.4f}")

questions = [
    "Как подобрать задания с учётом уровня студента?",
    "Как оценить качество обученной модели?",
    "Как найти похожие документы по смыслу?",
]

for question in questions:
    search(question)

print("\nПроверка поиска завершена.")
