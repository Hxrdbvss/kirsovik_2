import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "http://127.0.0.1:8003/ask"

# Ожидаемые документы выбраны вручную по известным текстам коллекции.
CASES = [
    {
        "question": "Как выяснить, что учащийся знает до начала обучения?",
        "expected_id": "ru_doc_2",
    },
    {
        "question": "Что помогает учащемуся разобраться в своих ошибках?",
        "expected_id": "ru_doc_3",
    },
    {
        "question": "Как проверить модель на данных, предназначенных для тестирования?",
        "expected_id": "ru_doc_8",
    },
    {
        "question": "Каким способом можно искать тексты по значению, а не только по словам?",
        "expected_id": "ru_doc_10",
    },
    {
        "question": "Сколько стоит обучение на этом курсе?",
        "expected_id": None,
        "expected_behavior": "Сообщить, что данных недостаточно.",
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
        raise SystemExit(
            f"Ошибка обращения к API: {error}\n"
            "Проверь, что сервер работает на порту 8003."
        )

    ids = [source["id"] for source in data["sources"]]
    expected_id = case["expected_id"]

    result = {
        "question": case["question"],
        "expected_id": expected_id,
        "expected_behavior": case.get("expected_behavior"),
        "retrieved_ids": ids,
        "hit_at_1": ids[0] == expected_id if expected_id else None,
        "hit_at_3": expected_id in ids[:3] if expected_id else None,
        "answer": data["answer"],
        "sources": data["sources"],
        "processing_time_seconds": data["processing_time_seconds"],
    }
    results.append(result)

    print("\n" + "=" * 60)
    print(f"Вопрос: {case['question']}")
    print(f"Найдено: {', '.join(ids)}")
    if expected_id:
        print(f"Ожидаемый документ: {expected_id}")
        print(f"На первом месте: {'да' if result['hit_at_1'] else 'нет'}")
        print(f"В первой тройке: {'да' if result['hit_at_3'] else 'нет'}")
    else:
        print(f"Ожидаемое поведение: {case['expected_behavior']}")
    print(f"Ответ: {data['answer']}", flush=True)

marked = [row for row in results if row["expected_id"] is not None]

summary = {
    "marked_questions": len(marked),
    "hit_at_1": sum(row["hit_at_1"] for row in marked) / len(marked),
    "hit_at_3": sum(row["hit_at_3"] for row in marked) / len(marked),
}

with open("paraphrase_evaluation.json", "w", encoding="utf-8") as file:
    json.dump(
        {"summary": summary, "results": results},
        file,
        ensure_ascii=False,
        indent=2,
    )

print("\n" + "=" * 60)
print(f"Размеченных вопросов: {summary['marked_questions']}")
print(f"Hit@1: {summary['hit_at_1']:.2f}")
print(f"Hit@3: {summary['hit_at_3']:.2f}")
print("Результаты сохранены: paraphrase_evaluation.json")
