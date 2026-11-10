import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "http://127.0.0.1:8003/ask"

# Ожидаемые документы размечены вручную для этой небольшой проверки.
CASES = [
    {
        "question": "Как подобрать задания с учётом уровня студента?",
        "expected_id": "ru_doc_1",
    },
    {
        "question": "Как определить начальный уровень знаний?",
        "expected_id": "ru_doc_2",
    },
    {
        "question": "Как обратная связь помогает студенту?",
        "expected_id": "ru_doc_3",
    },
    {
        "question": "Как оценить качество обученной модели?",
        "expected_id": "ru_doc_8",
    },
    {
        "question": "Как найти похожие документы по смыслу?",
        "expected_id": "ru_doc_10",
    },
]

results = []

for case in CASES:
    payload = json.dumps(
        {"question": case["question"]},
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"\nОшибка обращения к API: {error}")
        print("Проверь, что сервер запущен на порту 8003.")
        raise SystemExit(1)

    retrieved_ids = [source["id"] for source in data["sources"]]
    expected_id = case["expected_id"]

    hit_at_1 = bool(retrieved_ids and retrieved_ids[0] == expected_id)
    hit_at_3 = expected_id in retrieved_ids[:3]

    result = {
        "question": case["question"],
        "expected_id": expected_id,
        "retrieved_ids": retrieved_ids,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "answer": data["answer"],
        "sources": data["sources"],
        "processing_time_seconds": data["processing_time_seconds"],
    }
    results.append(result)

    print(f"\nВопрос: {case['question']}")
    print(f"Ожидаемый документ: {expected_id}")
    print(f"Найдено: {', '.join(retrieved_ids)}")
    print(f"Первое место: {'да' if hit_at_1 else 'нет'}")
    print(f"В первой тройке: {'да' if hit_at_3 else 'нет'}")
    print(f"Ответ: {data['answer']}", flush=True)

summary = {
    "questions_count": len(results),
    "hit_at_1": sum(row["hit_at_1"] for row in results) / len(results),
    "hit_at_3": sum(row["hit_at_3"] for row in results) / len(results),
}

output = {
    "description": (
        "Учебная проверка поиска на пяти вручную размеченных вопросах."
    ),
    "summary": summary,
    "results": results,
}

with open("retrieval_evaluation.json", "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False, indent=2)

print("\n" + "=" * 60)
print(f"Вопросов: {summary['questions_count']}")
print(f"Hit@1: {summary['hit_at_1']:.2f}")
print(f"Hit@3: {summary['hit_at_3']:.2f}")
print("Результаты сохранены: retrieval_evaluation.json")
