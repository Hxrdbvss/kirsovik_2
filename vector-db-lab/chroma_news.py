import chromadb
import torch
from sentence_transformers import SentenceTransformer

model_name = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)
device = "cuda" if torch.cuda.is_available() else "cpu"

print("Загрузка модели...")
model = SentenceTransformer(model_name, device=device)

client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(
    name="news_examples_ru",
    metadata={"hnsw:space": "cosine"},
)

# Условные сообщения для демонстрации поиска.
documents = [
    "Школа внедряет систему подбора учебных заданий по уровню знаний.",
    "Университет запускает курс по анализу данных и машинному обучению.",
    "Исследователи представили новую модель для обработки текстов.",
    "Банк внедряет систему обнаружения подозрительных операций.",
    "Компания представила новые серверы для хранения данных.",
]

metadata = [
    {"category": "education", "date": "2026-10-01"},
    {"category": "education", "date": "2026-10-02"},
    {"category": "technology", "date": "2026-10-03"},
    {"category": "finance", "date": "2026-10-04"},
    {"category": "technology", "date": "2026-10-05"},
]

ids = [f"news_{i + 1}" for i in range(len(documents))]

embeddings = model.encode(
    documents,
    convert_to_numpy=True,
).tolist()

collection.upsert(
    ids=ids,
    documents=documents,
    embeddings=embeddings,
    metadatas=metadata,
)

print(f"\nСообщений в коллекции: {collection.count()}")

def search(query, category=None):
    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
    ).tolist()

    options = {
        "query_embeddings": query_embedding,
        "n_results": 2,
        "include": ["documents", "distances", "metadatas"],
    }

    if category:
        options["where"] = {"category": category}

    result = collection.query(**options)

    print(f"\nЗапрос: {query}")
    if category:
        print(f"Фильтр: {category}")

    for i, (document, distance, meta) in enumerate(
        zip(
            result["documents"][0],
            result["distances"][0],
            result["metadatas"][0],
        ),
        start=1,
    ):
        print(f"{i}. {document}")
        print(
            f"   Категория: {meta['category']}; "
            f"дата: {meta['date']}; "
            f"расстояние: {distance:.4f}"
        )

search("Новые технологии для обработки текстов")
search("Учебные программы и задания для студентов", category="education")

print("\nГотово. Новостная коллекция сохранена в chroma_db.")
