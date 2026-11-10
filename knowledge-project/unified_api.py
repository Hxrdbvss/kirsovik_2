import json
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from learning_core import router as learning_router
from learning_core import materials as local_materials
from learning_core import get_progress, learning_path
from academy_core import router as academy_router, ensure_academy, admin_password

RAG_URL = "http://127.0.0.1:8003/ask-with-graph"
CATALOG_URL = "http://127.0.0.1:8005/search-with-graph"

app = FastAPI(title="Адаптивное обучение", version="1.0.0")
app.include_router(learning_router)
app.include_router(academy_router)


@app.get('/health')
def health():
    ensure_academy()
    admin_password()
    from learning_core import all_materials
    return {'status': 'ready', 'mode': 'local_learning', 'materials': len(all_materials()), 'disciplines': 10, 'groups': 2}


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    level: Literal["начальный", "продвинутый"] | None = None
    top_k: int = Field(default=3, ge=1, le=10)
    use_graph: bool = False

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Вопрос не должен быть пустым.")
        return value


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Не удалось обратиться к сервису {url}: {error}",
        ) from error


@app.post("/ask")
def ask(request: AskRequest):
    catalog = post_json(CATALOG_URL, {
        "query": request.question,
        "level": request.level,
        "top_k": request.top_k,
    })

    graph_facts = []

    for material in catalog["results"] if request.use_graph else []:
        if material.get("graph_status") != "ok":
            continue

        for topic in material.get("graph_topics", []):
            topic_name = topic.get("topic")
            if not topic_name:
                continue

            for prerequisite in topic.get("prerequisites", []):
                if prerequisite:
                    graph_facts.append(
                        f"Тема «{prerequisite}» указана в графе как "
                        f"предшествующая теме «{topic_name}»."
                    )

    graph_facts = list(dict.fromkeys(graph_facts))[:10]

    rag = post_json(RAG_URL, {
        "question": request.question,
        "graph_facts": graph_facts,
    })

    return {
        "question": request.question,
        "rag_answer": rag["answer"],
        "rag_sources": rag["sources"],
        "graph_facts": graph_facts,
        "catalog_results": catalog["results"],
    }


@app.post("/ask-manual")
def ask_manual(request: AskRequest):
    """Ответ по методичке с указанием найденных страниц PDF."""
    rag = post_json(
        "http://127.0.0.1:8003/ask-manual",
        {"question": request.question},
    )

    return {
        "question": rag["question"],
        "answer": rag["answer"],
        "sources": rag["sources"],
        "processing_time_seconds": rag["processing_time_seconds"],
    }


class AdaptiveRequest(BaseModel):
    code_module: str = Field(min_length=1, max_length=20)
    date_registration: float = Field(le=30)
    num_of_prev_attempts: int = Field(ge=0)
    studied_credits: int = Field(ge=0)
    vle_clicks: int = Field(ge=0)
    vle_records: int = Field(ge=0)
    submitted_count: int = Field(ge=0)

    topic_query: str = Field(
        min_length=1,
        max_length=1000,
        description="Тема для демонстрационного поиска материала",
    )

    @field_validator("topic_query")
    @classmethod
    def validate_topic_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Тема не должна быть пустой.")
        return value


@app.post("/adaptive-recommendation")
def adaptive_recommendation(request: AdaptiveRequest):
    """Демонстрация: прогноз риска и поиск материала по теме."""
    risk_payload = request.model_dump(exclude={"topic_query"})

    risk = post_json(
        "http://127.0.0.1:8007/predict-risk",
        risk_payload,
    )

    if risk["risk_flag"]:
        catalog = post_json(
            "http://127.0.0.1:8005/search-with-graph",
            {
                "query": request.topic_query,
                "level": "начальный",
                "top_k": 2,
            },
        )
        materials = catalog["results"]
        message = "Предложить дополнительные материалы для повторения."
    else:
        materials = []
        message = "Продолжить обучение по текущему плану."

    return {
        "risk": risk,
        "topic_query": request.topic_query,
        "message": message,
        "materials": materials,
        "note": (
            "Демонстрационное правило: тема введена пользователем; "
            "связь модели OULAD с материалами каталога не оценивалась."
        ),
    }


class GamificationRequest(BaseModel):
    completed_materials: int = Field(
        ge=0,
        le=10000,
        description="Количество изученных материалов",
    )
    completed_tasks: int = Field(
        ge=0,
        le=10000,
        description="Количество выполненных заданий",
    )


@app.post("/gamification-preview")
def gamification_preview(request: GamificationRequest):
    """Демонстрационный расчёт баллов без сохранения прогресса."""
    material_points = request.completed_materials * 10
    task_points = request.completed_tasks * 20
    total_points = material_points + task_points

    achievements = []

    if request.completed_materials >= 1:
        achievements.append("Первый изученный материал")

    if request.completed_tasks >= 1:
        achievements.append("Первое выполненное задание")

    if request.completed_tasks >= 5:
        achievements.append("Пять выполненных заданий")

    return {
        "completed_materials": request.completed_materials,
        "completed_tasks": request.completed_tasks,
        "material_points": material_points,
        "task_points": task_points,
        "total_points": total_points,
        "achievements": achievements,
        "note": (
            "Демонстрационный расчёт по переданным данным; "
            "история действий не сохраняется и не проверяется."
        ),
    }


from pathlib import Path


class StudentDashboardRequest(AdaptiveRequest):
    student_id: str = Field(
        min_length=1,
        max_length=100,
        description="Идентификатор студента в учебном прототипе",
    )

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Идентификатор студента не должен быть пустым.")
        return value


@app.post("/student-dashboard")
def student_dashboard(request: StudentDashboardRequest):
    """Демонстрация прогноза, рекомендаций и сохранённого прогресса."""
    adaptive_data = request.model_dump(exclude={"student_id"})
    adaptive_request = AdaptiveRequest(**adaptive_data)

    # Получаем прогноз напрямую: прежний семантический подбор
    # здесь не вызываем.
    risk_payload = adaptive_request.model_dump(exclude={"topic_query"})
    risk = post_json(
        "http://127.0.0.1:8007/predict-risk",
        risk_payload,
    )

    progress = get_progress(request.student_id)

    topic_result = topic_materials(
        TopicMaterialsRequest(
            student_id=request.student_id,
            topic=request.topic_query,
        )
    )
    materials = topic_result['materials']
    message = topic_result['message']

    adaptive = {
        "risk": risk,
        "topic_query": request.topic_query,
        "message": message,
        "materials": materials,
        "note": (
            "Демонстрационное правило: требуется точное название темы; "
            "связь модели OULAD с каталогом не оценивалась."
        ),
    }

    return {
        "student_id": request.student_id,
        "adaptive": adaptive,
        "progress": progress,
        "note": (
            "Учебный прототип: прогноз использует признаки OULAD, "
            "тема задаётся пользователем, а действия не проверяются."
        ),
    }


class TopicMaterialsRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=1000)

    @field_validator("student_id", "topic")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Поле не должно быть пустым.")
        return value


@app.post("/topic-materials")
def topic_materials(request: TopicMaterialsRequest):
    """Точный выбор темы и исключение освоенных по тесту материалов."""
    selected_topic = request.topic.casefold()
    matching = [
        material
        for material in learning_path(request.student_id)['materials']
        if material.get("topic", "").strip().casefold() == selected_topic
    ]
    available = [material for material in matching if not material['mastered']]

    if not matching:
        message = "Тема не найдена в локальном каталоге."
    elif not available:
        message = "Тема освоена по результату теста. Материал доступен для повторения во вкладке обучения."
    else:
        message = "Найдены новые материалы по выбранной теме."

    return {
        "student_id": request.student_id,
        "topic": request.topic,
        "message": message,
        "materials": available,
        "note": (
            "Материалы выбираются из локального каталога по точному совпадению темы."
        ),
    }


@app.get("/material-content/{material_id}")
def material_content(material_id: str):
    """Получить учебный текст для карточки материала."""
    content_path = Path(__file__).resolve().parent / "material_content.json"

    if not content_path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Файл с учебными материалами не найден.",
        )

    try:
        with content_path.open(encoding="utf-8") as file:
            materials = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=503,
            detail="Не удалось прочитать учебные материалы.",
        ) from error

    material = materials.get(material_id)

    if material is None:
        raise HTTPException(
            status_code=404,
            detail="Текст для этого материала пока не добавлен.",
        )

    return {"id": material_id, **material}
