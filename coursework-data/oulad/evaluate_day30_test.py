from pathlib import Path
import json

import joblib
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

train = pd.read_csv(ROOT / "prepared" / "students_day30_train.csv")
test = pd.read_csv(ROOT / "prepared" / "students_day30_test.csv")

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

assert not set(train["id_student"]) & set(test["id_student"])
assert set(test["target_risk"].unique()) == {0, 1}

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

y_true = test["target_risk"]
probabilities = model.predict_proba(test[features])[:, 1]
predictions = (probabilities >= threshold).astype(int)

tn, fp, fn, tp = confusion_matrix(
    y_true,
    predictions,
    labels=[0, 1],
).ravel()

metrics = {
    "accuracy": accuracy_score(y_true, predictions),
    "precision_risk": precision_score(y_true, predictions, zero_division=0),
    "recall_risk": recall_score(y_true, predictions, zero_division=0),
    "f1_risk": f1_score(y_true, predictions, zero_division=0),
    "roc_auc": roc_auc_score(y_true, probabilities),
    "average_precision": average_precision_score(y_true, probabilities),
    "confusion_matrix": {
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
    },
}

print("Модель: логистическая регрессия")
print("Порог:", threshold)
print("Записей в тесте:", len(test))
print("Студентов в тесте:", test["id_student"].nunique())

for name, value in metrics.items():
    if isinstance(value, (float, np.floating)):
        print(f"{name}: {value:.4f}")
    else:
        print(f"{name}: {value}")

# Показываем полноту отдельно для двух исходных неблагоприятных итогов.
print("\nВыявление риска по исходным категориям:")
category_results = {}
for category in ["Fail", "Withdrawn"]:
    mask = test["final_result"].eq(category).to_numpy()
    count = int(mask.sum())
    detected = int(predictions[mask].sum())
    category_results[category] = {
        "count": count,
        "detected": detected,
        "recall": detected / count if count else None,
    }
    print(f"{category}: {detected} из {count}")

results_dir = ROOT / "results"
models_dir = ROOT / "models"
results_dir.mkdir(exist_ok=True)
models_dir.mkdir(exist_ok=True)

result_path = results_dir / "day30_logistic_test.json"
result_path.write_text(
    json.dumps(
        {
            "model": "logistic_regression",
            "threshold": threshold,
            "threshold_selection": "validation",
            "features": features,
            "metrics": metrics,
            "category_results": category_results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

model_path = models_dir / "day30_logistic.joblib"
joblib.dump(model, model_path)

print("\nМетрики сохранены:", result_path)
print("Модель сохранена:", model_path)
