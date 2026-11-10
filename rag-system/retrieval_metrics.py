import json
from pathlib import Path

INPUT = Path("retrieval_evaluation.json")
OUTPUT = Path("retrieval_metrics.json")
K = 3

if not INPUT.is_file():
    raise SystemExit(f"Не найден файл {INPUT}. Сначала запусти evaluate_retrieval.py.")

with INPUT.open(encoding="utf-8") as file:
    rows = json.load(file)["results"]

if not rows:
    raise SystemExit("В файле нет результатов для оценки.")

results = []

for row in rows:
    relevant = {row["expected_id"]}
    retrieved = row["retrieved_ids"][:K]

    found = len(set(retrieved) & relevant)
    precision = found / K
    recall = found / len(relevant)

    reciprocal_rank = 0.0
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            reciprocal_rank = 1.0 / rank
            break

    results.append({
        "question": row["question"],
        "relevant_ids": sorted(relevant),
        "retrieved_ids": retrieved,
        "precision_at_3": precision,
        "recall_at_3": recall,
        "reciprocal_rank_at_3": reciprocal_rank,
    })

def average(key):
    return sum(row[key] for row in results) / len(results)

summary = {
    "questions": len(results),
    "precision_at_3": average("precision_at_3"),
    "recall_at_3": average("recall_at_3"),
    "mrr_at_3": average("reciprocal_rank_at_3"),
}

with OUTPUT.open("w", encoding="utf-8") as file:
    json.dump(
        {
            "note": (
                "Для каждого вопроса размечен один ожидаемый документ; "
                "оценка ограничена первыми тремя результатами."
            ),
            "summary": summary,
            "results": results,
        },
        file,
        ensure_ascii=False,
        indent=2,
    )

print(f"Вопросов: {summary['questions']}")
print(f"Precision@3: {summary['precision_at_3']:.3f}")
print(f"Recall@3: {summary['recall_at_3']:.3f}")
print(f"MRR@3: {summary['mrr_at_3']:.3f}")
print(f"Результаты сохранены: {OUTPUT}")
