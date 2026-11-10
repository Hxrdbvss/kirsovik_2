import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8004"


def call_api(method, path, body=None):
    payload = None
    headers = {}

    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        BASE_URL + path,
        data=payload,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=120) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


checks = []


def check(name, passed, details):
    checks.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}: {name} — {details}")


try:
    status, data = call_api("GET", "/health")
    check(
        "Состояние сервиса",
        status == 200 and data.get("status") == "ready",
        f"HTTP {status}, статус: {data.get('status')}",
    )
    check(
        "Количество материалов",
        status == 200 and data.get("documents") == 4,
        f"документов: {data.get('documents')}",
    )

    status, data = call_api("POST", "/search", {
        "query": "Материал про деревья решений",
        "level": "начальный",
        "top_k": 3,
    })
    results = data.get("results", [])
    check(
        "Поиск деревьев решений",
        status == 200 and bool(results) and results[0].get("id") == "mat_02",
        f"HTTP {status}, ID: {[row.get('id') for row in results]}",
    )
    check(
        "Фильтр начального уровня",
        bool(results) and all(row.get("level") == "начальный" for row in results),
        f"уровни: {[row.get('level') for row in results]}",
    )

    status, data = call_api("POST", "/search", {
        "query": "Методы ансамблевого обучения",
        "level": "продвинутый",
        "top_k": 3,
    })
    results = data.get("results", [])
    check(
        "Фильтр продвинутого уровня",
        status == 200
        and bool(results)
        and all(row.get("level") == "продвинутый" for row in results),
        f"HTTP {status}, ID: {[row.get('id') for row in results]}",
    )

    status, _ = call_api("POST", "/search", {
        "query": "   ",
        "top_k": 3,
    })
    check("Пустой запрос", status == 422, f"HTTP {status}")

    status, _ = call_api("POST", "/search", {
        "query": "Машинное обучение",
        "level": "несуществующий",
        "top_k": 3,
    })
    check("Неизвестный уровень", status == 422, f"HTTP {status}")

    status, _ = call_api("POST", "/search", {
        "query": "Машинное обучение",
        "top_k": 0,
    })
    check("Недопустимый top_k", status == 422, f"HTTP {status}")

    print(f"\nПройдено проверок: {sum(checks)} из {len(checks)}")

    if not all(checks):
        raise SystemExit(1)

except URLError as error:
    raise SystemExit(
        f"Не удалось подключиться к сервису: {error}\n"
        "Проверь, что сервер работает на порту 8004."
    )
