import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

URL = "http://127.0.0.1:8006/ask"


def ask(payload):
    request = Request(
        URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


checks = []


def check(name, condition):
    checks.append(condition)
    print(f"{'PASS' if condition else 'FAIL'}: {name}")


forest = {
    "question": "Что нужно изучить перед случайным лесом?",
    "level": "продвинутый",
    "top_k": 1,
}

status, without_graph = ask({**forest, "use_graph": False})
check("Запрос без графа", status == 200)
check("Факты не переданы", without_graph.get("graph_facts") == [])

status, with_graph = ask({**forest, "use_graph": True})
facts = with_graph.get("graph_facts", [])
check("Запрос с графом", status == 200)
check(
    "Связь случайного леса и деревьев решений",
    any("Деревья решений" in fact and "Случайный лес" in fact for fact in facts),
)

status, trees = ask({
    "question": "Что нужно изучить перед деревьями решений?",
    "level": "начальный",
    "top_k": 1,
    "use_graph": True,
})
facts = trees.get("graph_facts", [])
check("Запрос о деревьях решений", status == 200)
check(
    "Связь с основами машинного обучения",
    any("Основы машинного обучения" in fact and "Деревья решений" in fact for fact in facts),
)

status, _ = ask({"question": "   "})
check("Пустой вопрос отклонён", status == 422)

print(f"\nПройдено проверок: {sum(checks)} из {len(checks)}")
