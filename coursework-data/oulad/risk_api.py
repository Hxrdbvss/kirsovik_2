from contextlib import asynccontextmanager
import json
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "day30_logistic.joblib"
METRICS_PATH = ROOT / "results" / "day30_logistic_test.json"

FEATURES = [
    "code_module",
    "date_registration",
    "num_of_prev_attempts",
    "studied_credits",
    "vle_clicks",
    "vle_records",
    "submitted_count",
]

state = {}


class StudentFeatures(BaseModel):
    code_module: str = Field(
        min_length=1,
        max_length=20,
        description="Код модуля из набора OULAD, например AAA",
    )
    date_registration: float = Field(
        le=30,
        description="День регистрации относительно начала курса",
    )
    num_of_prev_attempts: int = Field(ge=0)
    studied_credits: int = Field(ge=0)
    vle_clicks: int = Field(
        ge=0,
        description="Сумма действий в VLE с 0-го по 30-й день",
    )
    vle_records: int = Field(
        ge=0,
        description="Количество записей активности с 0-го по 30-й день",
    )
    submitted_count: int = Field(
        ge=0,
        description="Число работ, отправленных с 0-го по 30-й день",
    )

    @field_validator("code_module")
    @classmethod
    def validate_module(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Код модуля не должен быть пустым.")
        return value


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MODEL_PATH.is_file():
        raise RuntimeError(f"Модель не найдена: {MODEL_PATH}")

    if not METRICS_PATH.is_file():
        raise RuntimeError(f"Файл с порогом не найден: {METRICS_PATH}")

    model = joblib.load(MODEL_PATH)

    with METRICS_PATH.open(encoding="utf-8") as file:
        metadata = json.load(file)

    threshold = float(metadata["threshold"])

    if not 0 <= threshold <= 1:
        raise RuntimeError("Порог должен быть между 0 и 1.")

    if list(model.feature_names_in_) != FEATURES:
        raise RuntimeError(
            "Ожидаемые признаки модели не совпадают со списком API."
        )

    if 1 not in model.classes_:
        raise RuntimeError("В модели не найден класс риска 1.")

    encoder = (
        model.named_steps["preprocess"]
        .named_transformers_["categorical"]
        .named_steps["encoder"]
    )

    state.update({
        "model": model,
        "threshold": threshold,
        "known_modules": set(encoder.categories_[0].tolist()),
    })

    print("Сервис прогноза готов к работе.", flush=True)
    yield
    state.clear()


app = FastAPI(
    title="Прогноз учебного риска",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ready",
        "model": "logistic_regression",
        "prediction_day": 30,
        "threshold": state["threshold"],
    }


@app.post("/predict-risk")
def predict_risk(request: StudentFeatures):
    if request.code_module not in state["known_modules"]:
        raise HTTPException(
            status_code=422,
            detail=(
                "Неизвестный код модуля. Для этой модели "
                "используй код из обучающего набора OULAD."
            ),
        )

    row = pd.DataFrame([request.model_dump()])[FEATURES]
    model = state["model"]

    risk_index = list(model.classes_).index(1)
    risk_score = float(model.predict_proba(row)[0, risk_index])

    high_risk = risk_score >= state["threshold"]

    return {
        "risk_score": round(risk_score, 4),
        "threshold": state["threshold"],
        "risk_flag": high_risk,
        "recommendation": (
            "Предложить дополнительные материалы и повторение темы."
            if high_risk
            else "Продолжить обучение по текущему плану."
        ),
        "note": (
            "Экспериментальная оценка по модели OULAD; "
            "прогноз не является оценкой способностей студента."
        ),
    }
