import json
import re
from collections import Counter
from pathlib import Path

INPUT = Path("answer_evaluation.json")
OUTPUT = Path("answer_rouge.json")


def tokenize(text):
    # Приводим слова к нижнему регистру; пунктуация не учитывается.
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def rouge1_f1(reference, answer):
    reference_tokens = tokenize(reference)
    answer_tokens = tokenize(answer)

    if not reference_tokens or not answer_tokens:
        return 0.0

    overlap = sum(
        (Counter(reference_tokens) & Counter(answer_tokens)).values()
    )

    precision = overlap / len(answer_tokens)
    recall = overlap / len(reference_tokens)

    if precision + recall == 0:
        return 0.0

    return 2 * precision * recall / (precision + recall)


if not INPUT.is_file():
    raise SystemExit(f"Не найден файл {INPUT}.")

with INPUT.open(encoding="utf-8") as file:
    rows = json.load(file)

if not rows:
    raise SystemExit("В файле нет ответов для сравнения.")

results = []

for row in rows:
    score = rouge1_f1(
        row["reference_answer"],
        row["model_answer"],
    )

    results.append({
        "question": row["question"],
        "reference_answer": row["reference_answer"],
        "model_answer": row["model_answer"],
        "rouge1_f1": score,
    })

    print("\nВопрос:", row["question"])
    print(f"ROUGE-1 F1: {score:.4f}")

average = sum(row["rouge1_f1"] for row in results) / len(results)

with OUTPUT.open("w", encoding="utf-8") as file:
    json.dump(
        {
            "metric": "ROUGE-1 F1",
            "tokenization": "Unicode words, lowercase, без стемминга",
            "count": len(results),
            "mean_rouge1_f1": average,
            "results": results,
        },
        file,
        ensure_ascii=False,
        indent=2,
    )

print(f"\nСредний ROUGE-1 F1: {average:.4f}")
print(f"Результаты сохранены: {OUTPUT}")
