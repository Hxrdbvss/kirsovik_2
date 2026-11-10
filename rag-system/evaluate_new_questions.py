import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "http://127.0.0.1:8003/ask"

questions = [
    "Что делает нейронная сеть во время обучения?",
    "Для чего нужна валидационная выборка?",
    "Где хранятся векторные представления документов?",
    "Какую видеокарту нужно купить для обучения модели?",
]

results = []

for question in questions:
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
    except (HTTPError, URLError, TimeoutError) as error:
        raise SystemExit(
            f"Не удалось обратиться к RAG-сервису: {error}\n"
            "Проверь, что сервер запущен на порту 8003."
        )

    results.append(data)

    print("\n" + "=" * 60)
    print("Вопрос:", data["question"])
    print("Ответ:", data["answer"])
    print("Источники:")
    for source in data["sources"]:
        print(
            f"- [{source['id']}] {source['text']} "
            f"(расстояние: {source['distance']:.4f})"
        )
    print(f"Время обработки: {data['processing_time_seconds']} с", flush=True)

with open("new_questions_evaluation.json", "w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)

print("\nРезультаты сохранены: new_questions_evaluation.json")
