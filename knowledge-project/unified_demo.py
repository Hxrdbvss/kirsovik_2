import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RAG_URL = "http://127.0.0.1:8003/ask"
CATALOG_URL = "http://127.0.0.1:8005/search-with-graph"


def post_json(url, payload):
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        return json.load(response)


question = input("Введите вопрос: ").strip()
if not question:
    raise SystemExit("Вопрос не должен быть пустым.")

try:
    rag = post_json(RAG_URL, {"question": question})
    catalog = post_json(CATALOG_URL, {
        "query": question,
        "level": None,
        "top_k": 3,
    })
except (HTTPError, URLError, TimeoutError) as error:
    raise SystemExit(
        f"Ошибка обращения к сервису: {error}\n"
        "Проверь RAG на порту 8003 и каталог на порту 8005."
    )

print("Вопрос:", question)
print("\nОтвет RAG:", rag["answer"])

print("\nФрагменты RAG:")
for source in rag["sources"]:
    print(f"- [{source['id']}] {source['text']}")

print("\nМатериалы каталога:")
for material in catalog["results"]:
    print(f"\n- [{material['id']}] {material['title']}")
    print(f"  Тема: {material['topic']}")
    print(f"  Уровень: {material['level']}")
    print(f"  Статус графа: {material['graph_status']}")

    for topic in material.get("graph_topics", []):
        prerequisites = topic.get("prerequisites", [])
        if prerequisites:
            print("  Предварительные темы:", ", ".join(prerequisites))

result = {
    "question": question,
    "rag": rag,
    "catalog": catalog,
}

with open("unified_demo_result.json", "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)

print("\nРезультат сохранён: unified_demo_result.json")
