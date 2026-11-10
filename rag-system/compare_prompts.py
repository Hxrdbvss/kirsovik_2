import json
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

PROMPTS = {
    "simple": (
        "Ответь на вопрос по контексту."
    ),
    "strict": (
        "Отвечай на русском языке, используя только информацию из контекста. "
        "Не используй собственные знания. Если контекст не содержит ответа "
        "на вопрос, напиши ровно: «Недостаточно данных для ответа»."
    ),
    "with_examples": (
        "Отвечай только по контексту и не добавляй новые факты. "
        "Если ответа в контексте нет, напиши: «Недостаточно данных для ответа».\n\n"
        "Пример 1:\n"
        "Контекст: Тестовая выборка нужна для оценки модели.\n"
        "Вопрос: Для чего нужна тестовая выборка?\n"
        "Ответ: Тестовая выборка нужна для оценки модели.\n\n"
        "Пример 2:\n"
        "Контекст: Тестовая выборка нужна для оценки модели.\n"
        "Вопрос: Какой язык программирования лучше?\n"
        "Ответ: Недостаточно данных для ответа."
    ),
}

CASES = [
    {
        "question": "Как подобрать задания с учётом уровня студента?",
        "context": (
            "[ru_doc_1] Адаптивное обучение подбирает задания с учётом знаний "
            "и прогресса студента.\n"
            "[ru_doc_8] Тестовая выборка помогает оценить качество обученной модели.\n"
            "[ru_doc_3] Обратная связь помогает студенту понять ошибки и исправить их."
        ),
    },
    {
        "question": "Как оценить качество обученной модели?",
        "context": (
            "[ru_doc_8] Тестовая выборка помогает оценить качество обученной модели.\n"
            "[ru_doc_1] Адаптивное обучение подбирает задания с учётом знаний "
            "и прогресса студента.\n"
            "[ru_doc_2] Диагностический тест помогает определить начальный уровень знаний."
        ),
    },
    {
        "question": "Какой язык программирования лучше всего изучать?",
        "context": (
            "[ru_doc_4] Начальный урок объясняет основные понятия машинного обучения.\n"
            "[ru_doc_10] Семантический поиск находит документы, близкие к запросу по смыслу.\n"
            "[ru_doc_1] Адаптивное обучение подбирает задания с учётом знаний "
            "и прогресса студента."
        ),
    },
]

device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if device == "cuda" else torch.float32

print(f"Устройство: {device}")
print(f"Загрузка модели: {MODEL_NAME}", flush=True)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    dtype=dtype,
).to(device)
model.eval()

results = []

for prompt_name, instruction in PROMPTS.items():
    print(f"\n{'=' * 60}")
    print(f"Инструкция: {prompt_name}", flush=True)

    for case in CASES:
        messages = [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": (
                    f"Контекст:\n{case['context']}\n\n"
                    f"Вопрос: {case['question']}"
                ),
            },
        ]

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(device)

        if device == "cuda":
            torch.cuda.synchronize()

        start = time.perf_counter()

        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=120,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        if device == "cuda":
            torch.cuda.synchronize()

        elapsed = time.perf_counter() - start
        generated = output[0, inputs["input_ids"].shape[1]:]
        answer = tokenizer.decode(
            generated, skip_special_tokens=True
        ).strip()

        results.append({
            "model": MODEL_NAME,
            "prompt_type": prompt_name,
            "instruction": instruction,
            "question": case["question"],
            "context": case["context"],
            "answer": answer,
            "generation_seconds": round(elapsed, 3),
        })

        print(f"\nВопрос: {case['question']}")
        print(f"Ответ: {answer}")
        print(f"Время: {elapsed:.2f} с", flush=True)

with open("prompt_comparison.json", "w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)

print("\nРезультаты сохранены: prompt_comparison.json")
