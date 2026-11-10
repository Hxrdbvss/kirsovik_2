import json
from pathlib import Path
from urllib.request import Request, urlopen

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "manual_chroma_db"

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

RAG_URL = "http://127.0.0.1:8003/ask-with-graph"

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_collection("lab_manual")

print("Загрузка модели эмбеддингов на CPU...")
embedder = SentenceTransformer(MODEL_NAME, device="cpu")

question = "Как отслеживать эксперименты машинного обучения с помощью MLflow?"

embedding = embedder.encode(
    [question],
    convert_to_numpy=True,
).tolist()

results = collection.query(
    query_embeddings=embedding,
    n_results=3,
    include=["documents", "metadatas", "distances"],
)

fragments = [
    {
        "text": text,
        "page": metadata["page"],
        "distance": float(distance),
    }
    for text, metadata, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )
]

# Временный эксперимент: используем существующее поле API
# для передачи фрагментов методички в модель.
payload = {
    "question": question,
    "graph_facts": [
        f"Методичка, страница PDF {fragment['page']}: {fragment['text']}"
        for fragment in fragments
    ],
}

request = Request(
    RAG_URL,
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urlopen(request, timeout=120) as response:
    answer = json.load(response)

print("\nВопрос:", question)
print("\nОтвет модели:")
print(answer.get("answer", ""))

print("\nПереданные фрагменты методички:")
for fragment in fragments:
    print(
        f"- Страница {fragment['page']}, "
        f"расстояние {fragment['distance']:.4f}"
    )

result = {
    "question": question,
    "answer": answer.get("answer"),
    "manual_fragments": fragments,
    "rag_response": answer,
}

output_path = PROJECT_DIR / "manual_answer_test.json"
output_path.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\nРезультат сохранён:", output_path)
