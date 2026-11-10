from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
data = pd.read_csv(ROOT / "prepared" / "students_day30_train.csv")

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

model.fit(fit[features], fit["target_risk"])

probabilities = model.predict_proba(val[features])[:, 1]
y_true = val["target_risk"]

results = []

print("Порог | Precision | Recall | F1     | FP  | FN")
print("-" * 55)

for threshold in np.arange(0.30, 0.61, 0.05):
    threshold = round(float(threshold), 2)
    predicted = (probabilities >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        predicted,
        labels=[0, 1],
    ).ravel()

    row = {
        "threshold": threshold,
        "precision": float(
            precision_score(y_true, predicted, zero_division=0)
        ),
        "recall": float(
            recall_score(y_true, predicted, zero_division=0)
        ),
        "f1": float(
            f1_score(y_true, predicted, zero_division=0)
        ),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
        "true_negative": int(tn),
    }

    results.append(row)

    print(
        f"{threshold:.2f}  | "
        f"{row['precision']:.4f}    | "
        f"{row['recall']:.4f} | "
        f"{row['f1']:.4f} | "
        f"{fp:3d} | {fn:3d}"
    )

output = ROOT / "results" / "day30_thresholds_validation.json"
output.parent.mkdir(exist_ok=True)
output.write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\nРезультаты сохранены:", output)
