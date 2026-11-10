import chromadb
import torch
from sentence_transformers import SentenceTransformer

model_name = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)
device = "cuda" if torch.cuda.is_available() else "cpu"

print("Загрузка многоязычной модели:", model_name)
print("Устройство:", device)

model = SentenceTransformer(model_name, device=device)

client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(
    name="learning_materials_ru",
    metadata={"hnsw:space": "cosine"},
)

documents = [
    "Адаптивное обучение подбирает задания с учётом знаний и прогресса студента.",
    "Диагностический тест помогает определить начальный уровень знаний.",
    "Обратная связь помогает студенту понять ошибки и исправить их.",
    "Начальный урок объясняет основные понятия машинного обучения.",
    "Нейронная сеть обучается находить закономерности в данных.",
    "Дерево решений делает прогноз, последовательно применяя правила.",
    "Валидационная выборка используется при настройке параметров модели.",
    "Тестовая выборка помогает оценить качество обученной модели.",
    "Векторная база данных хранит эмбеддинги документов.",
    "Семантический поиск находит документы, близкие к запросу по смыслу.",
]

categories = [
    "education",
    "education",
    "education",
    "machine_learning",
    "machine_learning",
    "machine_learning",
    "evaluation",
    "evaluation",
    "search",
    "search",
]

ids = [f"ru_doc_{i + 1}" for i in range(len(documents))]
metadata = [{"category": category} for category in categories]

print("\nСоздание эмбеддингов...")
embeddings = model.encode(
    documents,
    convert_to_numpy=True,
    show_progress_bar=True,
).tolist()

collection.upsert(
    ids=ids,
    documents=documents,
    embeddings=embeddings,
    metadatas=metadata,
)

print("Документов в русскоязычной коллекции:", collection.count())

queries = [
    "Как подобрать задания с учётом уровня студента?",
    "Как узнать качество обученной модели?",
    "Как найти похожие тексты по смыслу?",
]

for query in queries:
    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
    ).tolist()

    result = collection.query(
        query_embeddings=query_embedding,
        n_results=3,
        include=["documents", "distances", "metadatas"],
    )

    print(f"\nЗапрос: {query}")

    for i, (text, distance, meta) in enumerate(
        zip(
            result["documents"][0],
            result["distances"][0],
            result["metadatas"][0],
        ),
        start=1,
    ):
        print(f"{i}. {text}")
        print(
            f"   Категория: {meta['category']}; "
            f"расстояние: {distance:.4f}"
        )

print("\nРусскоязычная коллекция сохранена.")
