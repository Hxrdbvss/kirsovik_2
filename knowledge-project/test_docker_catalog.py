import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8005"


def call(method, path, body=None):
    data = None
    headers = {}

    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        BASE_URL + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=120) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


checks = []


def check(name, passed, detail):
    checks.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}: {name} — {detail}")


try:
    status, health = call("GET", "/health")
    check(
        "Сервис и каталог",
        status == 200
        and health.get("status") == "ready"
        and health.get("documents") == 4,
        f"HTTP {status}, документов: {health.get('documents')}",
    )

    status, response = call("POST", "/search-with-graph", {
        "query": "Метод случайного леса",
        "level": "продвинутый",
        "top_k": 1,
    })

    results = response.get("results", [])
    material = results[0] if results else {}
    topics = material.get("graph_topics", [])
    prerequisites = [
        item
        for topic in topics
        for item in topic.get("prerequisites", [])
    ]

    check(
        "Поиск в ChromaDB",
        status == 200 and material.get("id") == "mat_03",
        f"HTTP {status}, ID: {material.get('id')}",
    )
    check(
        "Подключение к Neo4j",
        material.get("graph_status") == "ok",
        f"статус: {material.get('graph_status')}",
    )
    check(
        "Предварительная тема",
        "Деревья решений" in prerequisites,
        f"найдено: {prerequisites}",
    )

    status, _ = call("GET", "/materials/unknown_id/graph")
    check("Несуществующий материал", status == 404, f"HTTP {status}")

    status, _ = call("POST", "/search", {"query": "   "})
    check("Пустой запрос", status == 422, f"HTTP {status}")

    print(f"\nПройдено проверок: {sum(checks)} из {len(checks)}")

    if not all(checks):
        raise SystemExit(1)

except URLError as error:
    raise SystemExit(f"Не удалось подключиться к API: {error}")
