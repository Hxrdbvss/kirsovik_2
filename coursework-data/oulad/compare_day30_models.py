from pathlib import Path
import json

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
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
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
data = pd.read_csv(ROOT / "prepared" / "students_day30_train.csv")

categorical = ["code_module"]
numeric = [
    "date_registration",
    "num_of_prev_attempts",
    "studied_credits",
    "vle_clicks",
    "vle_records",
    "submitted_count",
]
features = categorical + numeric

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.2,
    random_state=42,
)

fit_idx, val_idx = next(
    splitter.split(data, groups=data["id_student"])
)

fit = data.iloc[fit_idx]
val = data.iloc[val_idx]

assert not set(fit["id_student"]) & set(val["id_student"])

X_fit, y_fit = fit[features], fit["target_risk"]
X_val, y_val = val[features], val["target_risk"]


def make_preprocessor(scale_numeric):
    numeric_steps = [("imputer", SimpleImputer(strategy="median"))]

    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))

    return ColumnTransformer([
        ("numeric", Pipeline(numeric_steps), numeric),
        (
            "categorical",
            Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("encoder", OneHotEncoder(handle_unknown="ignore")),
            ]),
            categorical,
        ),
    ])


models = {
    "baseline_majority": DummyClassifier(strategy="most_frequent"),

    "logistic_regression": Pipeline([
        ("preprocess", make_preprocessor(scale_numeric=True)),
        (
            "classifier",
            LogisticRegression(max_iter=1000, random_state=42),
        ),
    ]),

    "random_forest": Pipeline([
        ("preprocess", make_preprocessor(scale_numeric=False)),
        (
            "classifier",
            RandomForestClassifier(
                n_estimators=200,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ]),
}

results = {}

print("Обучение:", len(fit), "записей")
print("Валидация:", len(val), "записей")
print(
    "Общих студентов:",
    len(set(fit["id_student"]) & set(val["id_student"])),
)

for name, model in models.items():
    print("\nОбучение модели:", name, flush=True)

    model.fit(X_fit, y_fit)
    predictions = model.predict(X_val)
    probabilities = model.predict_proba(X_val)[:, 1]

    tn, fp, fn, tp = confusion_matrix(
        y_val,
        predictions,
        labels=[0, 1],
    ).ravel()

    metrics = {
        "accuracy": accuracy_score(y_val, predictions),
        "precision_risk": precision_score(y_val, predictions, zero_division=0),
        "recall_risk": recall_score(y_val, predictions, zero_division=0),
        "f1_risk": f1_score(y_val, predictions, zero_division=0),
        "roc_auc": roc_auc_score(y_val, probabilities),
        "average_precision": average_precision_score(y_val, probabilities),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }

    results[name] = metrics

    print("\nМодель:", name)
    for metric, value in metrics.items():
        if isinstance(value, float):
            print(f"  {metric}: {value:.4f}")
        else:
            print(f"  {metric}: {value}")

output = ROOT / "results"
output.mkdir(exist_ok=True)

path = output / "day30_model_comparison_validation.json"
path.write_text(
    json.dumps(
        {
            "split": "grouped_validation_from_training",
            "features": features,
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print("\nРезультаты сохранены:", path)
