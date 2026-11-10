from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parent
data_path = ROOT / "prepared" / "students_day30.csv"

data = pd.read_csv(data_path)

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.2,
    random_state=42,
)

train_idx, test_idx = next(
    splitter.split(data, groups=data["id_student"])
)

train = data.iloc[train_idx].copy()
test = data.iloc[test_idx].copy()

train_students = set(train["id_student"])
test_students = set(test["id_student"])
overlap = train_students & test_students

assert not overlap, "Один и тот же студент попал в обе выборки."
assert len(train) + len(test) == len(data)
assert set(data["target_risk"].unique()) == {0, 1}

output = ROOT / "prepared"
train.to_csv(output / "students_day30_train.csv", index=False)
test.to_csv(output / "students_day30_test.csv", index=False)

print("Обучающая выборка:")
print("  Записей:", len(train))
print("  Студентов:", train["id_student"].nunique())
print("  Доля риска:", round(train["target_risk"].mean(), 4))

print("\nТестовая выборка:")
print("  Записей:", len(test))
print("  Студентов:", test["id_student"].nunique())
print("  Доля риска:", round(test["target_risk"].mean(), 4))

print("\nОбщих студентов:", len(overlap))

print("\nИсходные результаты в тестовой выборке:")
print(test["final_result"].value_counts())

print("\nФайлы сохранены в:", output)
