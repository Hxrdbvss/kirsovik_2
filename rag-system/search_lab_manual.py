from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "manual_chroma_db"
MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

if not DB_PATH.is_dir():
    raise FileNotFoundError(f"База не найдена: {DB_PATH}")

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_collection("lab_manual")

print("Фрагментов в коллекции:", collection.count())
print("Загрузка модели эмбеддингов на CPU...")
embedder = SentenceTransformer(MODEL_NAME, device="cpu")

questions = [
    "Как отслеживать эксперименты машинного обучения с помощью MLflow?",
    "Как выполнить семантический поиск с помощью ChromaDB?",
    "Как запустить приложение FastAPI в Docker?",
]

for question in questions:
    embedding = embedder.encode(
        [question],
        convert_to_numpy=True,
    ).tolist()

    results = collection.query(
        query_embeddings=embedding,
        n_results=min(3, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    print("\n" + "=" * 60)
    print("Запрос:", question)

    for rank, (text, metadata, distance) in enumerate(
        zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ),
        start=1,
    ):
        print(f"\n{rank}. Страница PDF: {metadata['page']}")
        print(f"   Расстояние: {distance:.4f}")
        print(f"   Текст: {text[:700]}")
