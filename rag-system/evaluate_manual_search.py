import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "manual_chroma_db"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

cases = [
    {
        "question": "Что такое MLflow Tracking?",
        "expected_pages": [12],
    },
    {
        "question": "Как отслеживать эксперименты с MLflow?",
        "expected_pages": [12, 28],
    },
    {
        "question": "Как выполнить семантический поиск с помощью ChromaDB?",
        "expected_pages": [35, 38],
    },
    {
        "question": "Как запустить приложение FastAPI в Docker?",
        "expected_pages": [85],
    },
]

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_collection("lab_manual")

print("Загрузка модели эмбеддингов на CPU...")
model = SentenceTransformer(MODEL, device="cpu")

rows = []

for case in cases:
    embedding = model.encode(
        [case["question"]],
        convert_to_numpy=True,
    ).tolist()

    found = collection.query(
        query_embeddings=embedding,
        n_results=min(3, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    sources = [
        {
            "id": doc_id,
            "page": metadata["page"],
            "distance": float(distance),
            "text": text,
        }
        for doc_id, metadata, distance, text in zip(
            found["ids"][0],
            found["metadatas"][0],
            found["distances"][0],
            found["documents"][0],
        )
    ]

    pages = [source["page"] for source in sources]
    expected = set(case["expected_pages"])

    hit_at_1 = bool(pages) and pages[0] in expected
    hit_at_3 = any(page in expected for page in pages)

    rows.append({
        **case,
        "sources": sources,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
    })

    print("\nВопрос:", case["question"])
    print("Ожидаемые страницы:", case["expected_pages"])
    print("Найденные страницы:", pages)
    print("Совпадение на первом месте:", "да" if hit_at_1 else "нет")
    print("Совпадение в тройке:", "да" if hit_at_3 else "нет")

count = len(rows)
summary = {
    "questions": count,
    "hit_at_1": sum(row["hit_at_1"] for row in rows) / count,
    "hit_at_3": sum(row["hit_at_3"] for row in rows) / count,
}

print("\n" + "=" * 60)
print("Вопросов:", count)
print(f"Hit@1: {summary['hit_at_1']:.2f}")
print(f"Hit@3: {summary['hit_at_3']:.2f}")
print("Оценка предварительная: проверьте разметку страниц и сами фрагменты.")

path = ROOT / "manual_retrieval_evaluation.json"
path.write_text(
    json.dumps(
        {"summary": summary, "results": rows},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print("Результаты сохранены:", path)
