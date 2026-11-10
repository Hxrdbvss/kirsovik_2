from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
data = pd.read_csv(ROOT / "prepared" / "students_day30.csv")

numeric = [
    "date_registration",
    "num_of_prev_attempts",
    "studied_credits",
    "vle_clicks",
    "vle_records",
    "submitted_count",
]
categorical = ["code_module"]
features = categorical + numeric
threshold = 0.35

train = data[
    data["code_presentation"].str.startswith("2013")
].copy()

future = data[
    data["code_presentation"].str.startswith("2014")
].copy()

train_students = set(train["id_student"])
test = future[~future["id_student"].isin(train_students)].copy()

known_modules = set(train["code_module"])
test_known = test[test["code_module"].isin(known_modules)].copy()
test_new_module = test[~test["code_module"].isin(known_modules)].copy()

assert not set(train["id_student"]) & set(test["id_student"])

preprocess = ColumnTransformer([
    (
        "numeric",
        Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]),
        numeric,
    ),
    (
        "categorical",
        Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore")),
        ]),
        categorical,
    ),
])

model = Pipeline([
    ("preprocess", preprocess),
    ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
])

model.fit(train[features], train["target_risk"])


def evaluate(name, subset):
    print("\n" + "=" * 60)
    print(name)
    print("Записей:", len(subset))
    print("Студентов:", subset["id_student"].nunique())

    if subset.empty:
        print("Нет данных для оценки.")
        return None

    y_true = subset["target_risk"]
    probabilities = model.predict_proba(subset[features])[:, 1]
    predictions = (probabilities >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true, predictions, labels=[0, 1]
    ).ravel()

    metrics = {
        "records": len(subset),
        "students": int(subset["id_student"].nunique()),
        "risk_share": float(y_true.mean()),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision_risk": float(
            precision_score(y_true, predictions, zero_division=0)
        ),
        "recall_risk": float(
            recall_score(y_true, predictions, zero_division=0)
        ),
        "f1_risk": float(
            f1_score(y_true, predictions, zero_division=0)
        ),
        "roc_auc": (
            float(roc_auc_score(y_true, probabilities))
            if y_true.nunique() == 2 else None
        ),
        "average_precision": (
            float(average_precision_score(y_true, probabilities))
            if y_true.nunique() == 2 else None
        ),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }

    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}")

    return metrics


print("Обучение на 2013:", len(train), "записей")
print("Всего записей 2014:", len(future))
print("Исключено записей студентов, встречавшихся в 2013:",
      len(future) - len(test))
print("Общих студентов после исключения:",
      len(set(train["id_student"]) & set(test["id_student"])))
print("Новые модули:", sorted(set(test["code_module"]) - known_modules))
print("Порог:", threshold)

results = {
    "all_2014_new_students": evaluate(
        "Все модули 2014, новые студенты",
        test,
    ),
    "known_modules": evaluate(
        "Модули, встречавшиеся в 2013",
        test_known,
    ),
    "new_modules": evaluate(
        "Новые модули",
        test_new_module,
    ),
}

output = ROOT / "results" / "day30_temporal_evaluation.json"
output.parent.mkdir(exist_ok=True)
output.write_text(
    json.dumps(
        {
            "train_period": "2013",
            "test_period": "2014",
            "threshold": threshold,
            "threshold_note": (
                "Выбран на предыдущей валидации, содержащей записи "
                "разных лет; не является независимым временным подбором."
            ),
            "features": features,
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print("\nРезультаты сохранены:", output)
