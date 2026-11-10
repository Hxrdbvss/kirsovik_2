import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8003"


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


def check(name, condition, details):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {name} — {details}", flush=True)
    return condition


try:
    checks = []

    status, health = call_api("GET", "/health")
    checks.append(check(
        "Состояние сервиса",
        status == 200 and health.get("status") == "ready",
        f"HTTP {status}, status={health.get('status')}",
    ))
    checks.append(check(
        "Коллекция документов",
        status == 200 and health.get("documents", 0) > 0,
        f"документов: {health.get('documents')}",
    ))

    status, response = call_api(
        "POST", "/ask",
        {"question": "Как определить начальный уровень знаний?"},
    )
    sources = response.get("sources", [])
    checks.append(check(
        "Ответ и источники",
        status == 200 and bool(response.get("answer")) and bool(sources),
        f"HTTP {status}, источников: {len(sources)}",
    ))
    checks.append(check(
        "Ожидаемый источник в первой тройке",
        any(source.get("id") == "ru_doc_2" for source in sources[:3]),
        f"найдены: {[source.get('id') for source in sources]}",
    ))

    status, response = call_api(
        "POST", "/ask", {"question": "   "}
    )
    checks.append(check(
        "Вопрос из пробелов",
        status == 422,
        f"HTTP {status}",
    ))

    status, response = call_api("POST", "/ask", {})
    checks.append(check(
        "Отсутствующее поле question",
        status == 422,
        f"HTTP {status}",
    ))

    status, response = call_api(
        "POST", "/ask", {"question": "а" * 1001}
    )
    checks.append(check(
        "Превышение длины вопроса",
        status == 422,
        f"HTTP {status}",
    ))

    print(f"\nПройдено проверок: {sum(checks)} из {len(checks)}")

    if not all(checks):
        raise SystemExit(1)

except URLError as error:
    raise SystemExit(
        f"Не удалось подключиться к сервису: {error}\n"
        "Проверь, что сервер запущен на порту 8003."
    )
