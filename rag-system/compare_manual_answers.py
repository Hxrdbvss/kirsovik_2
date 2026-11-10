import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

URL = "http://127.0.0.1:8003/ask-manual"

cases = [
    {
        "question": "Что такое MLflow Tracking?",
        "keywords": ["mlflow tracking"],
    },
    {
        "question": "Как отслеживать эксперименты машинного обучения с помощью MLflow?",
        "keywords": ["логирования", "логировать", "параметр", "метрик"],
    },
    {
        "question": "Как выполнить семантический поиск с помощью ChromaDB?",
        "keywords": ["семантическ", "поиск"],
    },
    {
        "question": "Сколько стоит обучение на этом курсе?",
        "keywords": ["стоимость", "цена", "стоит"],
    },
]


def ask(question):
    payload = json.dumps(
        {"question": question},
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        return json.load(response)


def find_sentences(sources, keywords):
    matches = []
    seen = set()

    for source in sources:
        text = source.get("text", "")

        # Простое разбиение: полезно для проверки, но не всегда
        # правильно обрабатывает сокращения и примеры кода.
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            normalized = sentence.casefold()

            if not sentence or normalized in seen:
                continue

            if any(word.casefold() in normalized for word in keywords):
                seen.add(normalized)
                matches.append({
                    "page": source.get("page"),
                    "text": sentence,
                })

    return matches[:5]


results = []

for case in cases:
    response = ask(case["question"])
    matches = find_sentences(response["sources"], case["keywords"])

    item = {
        "question": case["question"],
        "generated_answer": response["answer"],
        "sources": response["sources"],
        "matching_sentences": matches,
    }
    results.append(item)

    print("\n" + "=" * 60)
    print("Вопрос:", case["question"])
    print("\nОтвет модели:", response["answer"])
    print("\nПредложения с ключевыми словами:")

    if matches:
        for match in matches:
            print(f"- Страница {match['page']}: {match['text'][:500]}")
    else:
        print("- Совпадений не найдено.")

output = Path("manual_answer_comparison.json")
output.write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\nРезультаты сохранены:", output.resolve())
