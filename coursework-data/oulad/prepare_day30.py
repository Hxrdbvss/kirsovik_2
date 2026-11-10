from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUTPUT = ROOT / "prepared"
OUTPUT.mkdir(exist_ok=True)

CUTOFF_DAY = 30
KEYS = ["code_module", "code_presentation", "id_student"]

students = pd.read_csv(RAW / "studentInfo.csv", na_values=["?"])
registration = pd.read_csv(
    RAW / "studentRegistration.csv",
    na_values=["?"],
)

data = students.merge(
    registration,
    on=KEYS,
    how="left",
    validate="one_to_one",
)

print("Исходных записей:", len(data))

# Для прогноза на 30-й день студент должен быть зарегистрирован
# и ещё не прекратить обучение.
eligible = (
    data["date_registration"].notna()
    & (data["date_registration"] <= CUTOFF_DAY)
    & (
        data["date_unregistration"].isna()
        | (data["date_unregistration"] > CUTOFF_DAY)
    )
)

# Для Withdrawn неизвестная дата не позволяет установить,
# оставался ли студент на курсе на 30-й день.
eligible &= ~(
    (data["final_result"] == "Withdrawn")
    & data["date_unregistration"].isna()
)

data = data.loc[eligible].copy()

print("Записей после отбора:", len(data))
print("Исключено:", len(students) - len(data))

print("\nИсходные результаты после отбора:")
print(data["final_result"].value_counts(dropna=False))

# 1 — неблагоприятный итог; 0 — успешный.
data["target_risk"] = data["final_result"].map({
    "Pass": 0,
    "Distinction": 0,
    "Fail": 1,
    "Withdrawn": 1,
})

if data["target_risk"].isna().any():
    raise ValueError("Обнаружены неизвестные значения final_result.")

# Из большого файла читаем только нужные столбцы и обрабатываем частями.
activity_parts = []

print("\nОбработка активности VLE...")
for chunk in pd.read_csv(
    RAW / "studentVle.csv",
    usecols=KEYS + ["date", "sum_click"],
    chunksize=500_000,
):
    # Используем активность с первого по 30-й день.
    chunk = chunk[
        (chunk["date"] >= 0)
        & (chunk["date"] <= CUTOFF_DAY)
    ]

    if chunk.empty:
        continue

    part = chunk.groupby(KEYS, as_index=False).agg(
        vle_clicks=("sum_click", "sum"),
        vle_records=("sum_click", "size"),
    )
    activity_parts.append(part)

if activity_parts:
    activity = pd.concat(activity_parts, ignore_index=True)
    activity = activity.groupby(KEYS, as_index=False).agg(
        vle_clicks=("vle_clicks", "sum"),
        vle_records=("vle_records", "sum"),
    )
else:
    activity = pd.DataFrame(columns=KEYS + ["vle_clicks", "vle_records"])

data = data.merge(activity, on=KEYS, how="left", validate="one_to_one")

for column in ["vle_clicks", "vle_records"]:
    data[column] = data[column].fillna(0).astype(int)

# Оценки соединяем с таблицей заданий, чтобы получить курс и его запуск.
assessments = pd.read_csv(RAW / "assessments.csv", na_values=["?"])
submissions = pd.read_csv(
    RAW / "studentAssessment.csv",
    na_values=["?"],
)

submissions = submissions.merge(
    assessments[["id_assessment", "code_module", "code_presentation"]],
    on="id_assessment",
    how="left",
    validate="many_to_one",
)

# Банкированные оценки исключаем из первого варианта:
# их происхождение может относиться к прежней попытке.
submissions = submissions[
    (submissions["date_submitted"] >= 0)
    & (submissions["date_submitted"] <= CUTOFF_DAY)
    & (submissions["is_banked"] == 0)
].copy()

scores = submissions.groupby(KEYS, as_index=False).agg(
    submitted_count=("id_assessment", "size"),
    score_count=("score", "count"),
    score_mean=("score", "mean"),
)

data = data.merge(scores, on=KEYS, how="left", validate="one_to_one")

for column in ["submitted_count", "score_count"]:
    data[column] = data[column].fillna(0).astype(int)

# score_mean остаётся пропущенным, если оценки ещё нет.
# При обучении его обработаем отдельно и только на обучающей выборке.
columns = KEYS + [
    "date_registration",
    "num_of_prev_attempts",
    "studied_credits",
    "vle_clicks",
    "vle_records",
    "submitted_count",
    "score_count",
    "score_mean",
    "final_result",
    "target_risk",
]

prepared = data[columns].copy()
path = OUTPUT / "students_day30.csv"
prepared.to_csv(path, index=False)

print("\nРаспределение целевой переменной:")
print(prepared["target_risk"].value_counts().sort_index())

print("\nПропуски средних оценок:", prepared["score_mean"].isna().sum())
print("Уникальных студентов:", prepared["id_student"].nunique())
print("\nПервые строки:")
print(prepared.head(5).to_string(index=False))

print("\nСохранено:", path)
