import json
from datetime import datetime
from pathlib import Path

files = {
    "generator_comparison": "generator_comparison.json",
    "prompt_comparison": "prompt_comparison.json",
    "retrieval_evaluation": "retrieval_evaluation.json",
    "answer_evaluation": "answer_evaluation.json",
    "paraphrase_evaluation": "paraphrase_evaluation.json",
    "prompt_manual_assessment": "prompt_manual_assessment.json",
    "new_questions_evaluation": "new_questions_evaluation.json",
}

collected = {
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "description": "Сохранённые результаты экспериментов с RAG-системой.",
    "experiments": {},
    "missing_files": [],
}

for name, filename in files.items():
    path = Path(filename)

    if not path.is_file():
        collected["missing_files"].append(filename)
        print(f"Не найден: {filename}")
        continue

    try:
        with path.open(encoding="utf-8") as file:
            collected["experiments"][name] = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        collected["missing_files"].append(filename)
        print(f"Не удалось прочитать {filename}: {error}")
        continue

    print(f"Добавлен: {filename}")

output = Path("rag_experiments_collected.json")

with output.open("w", encoding="utf-8") as file:
    json.dump(collected, file, ensure_ascii=False, indent=2)

print(f"\nСохранено: {output.resolve()}")
print(f"Добавлено файлов: {len(collected['experiments'])}")
print(f"Не найдено или не прочитано: {len(collected['missing_files'])}")
