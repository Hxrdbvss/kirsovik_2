import json
from pathlib import Path
from urllib.request import Request, urlopen

API_URL = "http://127.0.0.1:8003/ask"
INPUT_FILE = Path("retrieval_evaluation.json")
OUTPUT_FILE = Path("answer_evaluation.json")

# Ожидаемые ответы составлены вручную по текстам документов.
references = {
    "ru_doc_1": (
        "Адаптивное обучение подбирает задания с учётом знаний "
        "и прогресса студента."
    ),
    "ru_doc_2": (
        "Диагностический тест помогает определить начальный уровень знаний."
    ),
    "ru_doc_3": (
        "Обратная связь помогает студенту понять ошибки и исправить их."
    ),
    "ru_doc_8": (
        "Тестовая выборка помогает оценить качество обученной модели."
    ),
    "ru_doc_10": (
        "Семантический поиск находит документы, близкие к запросу по смыслу."
    ),
}

if not INPUT_FILE.is_file():
    raise SystemExit(
        f"Файл {INPUT_FILE} не найден. Сначала запусти evaluate_retrieval.py."
    )

with INPUT_FILE.open(encoding="utf-8") as file:
    retrieval_results = json.load(file)["results"]

results = []

for row in retrieval_results:
    expected_id = row["expected_id"]

    results.append({
        "question": row["question"],
        "reference_answer": references[expected_id],
        "model_answer": row["answer"],
        "expected_source": expected_id,
        "retrieved_sources": row["retrieved_ids"],
        "manual_assessment": None,
    })

# Проверка вопроса, ответа на который нет в нашей коллекции.
question = "Какой язык программирования лучше всего изучать?"
payload = json.dumps(
    {"question": question},
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
except Exception as error:
    raise SystemExit(
        f"Не удалось обратиться к API: {error}\n"
        "Проверь, что сервер запущен на порту 8003."
    )

results.append({
    "question": question,
    "reference_answer": "Недостаточно данных для ответа.",
    "model_answer": data["answer"],
    "expected_source": None,
    "retrieved_sources": [source["id"] for source in data["sources"]],
    "manual_assessment": None,
})

for number, row in enumerate(results, start=1):
    print(f"\n{'=' * 60}")
    print(f"Пример {number}")
    print(f"Вопрос: {row['question']}")
    print(f"Ожидаемый ответ: {row['reference_answer']}")
    print(f"Ответ модели: {row['model_answer']}")
    print(f"Найденные документы: {', '.join(row['retrieved_sources'])}")

with OUTPUT_FILE.open("w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)

print(f"\nРезультаты сохранены: {OUTPUT_FILE}")
print("Поле manual_assessment оставлено для последующей ручной оценки.")
