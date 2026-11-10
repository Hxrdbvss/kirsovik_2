import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

INPUT = Path("answer_evaluation.json")
OUTPUT = Path("answer_similarity.json")
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

if not INPUT.is_file():
    raise SystemExit(f"Не найден файл {INPUT}.")

with INPUT.open(encoding="utf-8") as file:
    rows = json.load(file)

if not rows:
    raise SystemExit("В файле нет ответов для сравнения.")

print("Загрузка модели эмбеддингов на CPU...", flush=True)
model = SentenceTransformer(MODEL, device="cpu")

references = [row["reference_answer"] for row in rows]
answers = [row["model_answer"] for row in rows]

reference_vectors = model.encode(
    references,
    convert_to_numpy=True,
    normalize_embeddings=True,
)
answer_vectors = model.encode(
    answers,
    convert_to_numpy=True,
    normalize_embeddings=True,
)

results = []

for row, ref_vector, answer_vector in zip(
    rows, reference_vectors, answer_vectors
):
    similarity = float(np.dot(ref_vector, answer_vector))

    results.append({
        "question": row["question"],
        "reference_answer": row["reference_answer"],
        "model_answer": row["model_answer"],
        "cosine_similarity": similarity,
    })

    print("\nВопрос:", row["question"])
    print("Эталон:", row["reference_answer"])
    print("Ответ: ", row["model_answer"])
    print(f"Косинусная схожесть: {similarity:.4f}")

average = sum(row["cosine_similarity"] for row in results) / len(results)

with OUTPUT.open("w", encoding="utf-8") as file:
    json.dump(
        {
            "embedding_model": MODEL,
            "count": len(results),
            "mean_cosine_similarity": average,
            "results": results,
        },
        file,
        ensure_ascii=False,
        indent=2,
    )

print(f"\nСредняя косинусная схожесть: {average:.4f}")
print(f"Результаты сохранены: {OUTPUT}")
