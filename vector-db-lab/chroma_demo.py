import chromadb
import torch
from sentence_transformers import SentenceTransformer

# При первом запуске модель загрузится из Hugging Face.
model_name = "sentence-transformers/all-MiniLM-L6-v2"
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Загрузка модели: {model_name}")
print(f"Устройство: {device}")

model = SentenceTransformer(model_name, device=device)

# База будет сохраняться на диске в папке chroma_db.
client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(
    name="learning_materials",
    metadata={"hnsw:space": "cosine"},
)

documents = [
    "Adaptive learning adjusts educational tasks to each student's progress.",
    "A diagnostic test helps estimate the student's current knowledge.",
    "A beginner's lesson introduces the basic concepts of machine learning.",
    "A neural network learns patterns from training data.",
    "A decision tree makes predictions using a sequence of rules.",
    "A validation dataset helps select model parameters.",
    "A test dataset is used to evaluate a trained model.",
    "A vector database stores embeddings for similarity search.",
    "Semantic search finds documents with related meanings.",
    "Feedback helps a student understand mistakes and improve.",
]

categories = [
    "education",
    "education",
    "machine_learning",
    "machine_learning",
    "machine_learning",
    "evaluation",
    "evaluation",
    "search",
    "search",
    "education",
]

ids = [f"doc_{i + 1}" for i in range(len(documents))]

metadata = [
    {"category": category, "source": "educational_example"}
    for category in categories
]

print("\nСоздание эмбеддингов документов...")
embeddings = model.encode(
    documents,
    convert_to_numpy=True,
    show_progress_bar=True,
).tolist()

# Повторный запуск обновит эти документы без создания дубликатов.
collection.upsert(
    ids=ids,
    documents=documents,
    embeddings=embeddings,
    metadatas=metadata,
)

print(f"\nДокументов в коллекции: {collection.count()}")

def semantic_search(query, n_results=3, category=None):
    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
    ).tolist()

    options = {
        "query_embeddings": query_embedding,
        "n_results": n_results,
        "include": ["documents", "distances", "metadatas"],
    }

    if category is not None:
        options["where"] = {"category": category}

    results = collection.query(**options)

    print(f"\nЗапрос: {query}")
    if category:
        print(f"Фильтр по категории: {category}")

    for index, (doc, distance, meta) in enumerate(
        zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ),
        start=1,
    ):
        print(f"{index}. {doc}")
        print(
            f"   Категория: {meta['category']}; "
            f"косинусное расстояние: {distance:.4f}"
        )

print("\n--- Семантический поиск ---")

semantic_search("How can learning tasks be adapted to a student?")
semantic_search("How do we search for documents by meaning?")
semantic_search("How can we check the quality of a trained model?")

print("\n--- Поиск с фильтрацией ---")

semantic_search(
    "How can we help a learner improve?",
    n_results=2,
    category="education",
)

print("\nГотово. База сохранена в папке chroma_db.")
