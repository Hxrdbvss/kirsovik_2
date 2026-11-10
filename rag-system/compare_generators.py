import gc
import json
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODELS = [
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
]

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
results = []

print(f"Устройство: {device}", flush=True)

for model_name in MODELS:
    print(f"\n{'=' * 60}\nМодель: {model_name}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=dtype,
    ).to(device)
    model.eval()

    for case in CASES:
        messages = [
            {
                "role": "system",
                "content": (
                    "Отвечай по-русски, используя только сведения из контекста. "
                    "Не добавляй факты, которых в нём нет. Если контекст не "
                    "содержит ответа, скажи: «Недостаточно данных для ответа»."
                ),
            },
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
            torch.cuda.reset_peak_memory_stats()

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
        answer = tokenizer.decode(generated, skip_special_tokens=True).strip()
        peak_gib = (
            torch.cuda.max_memory_allocated() / 1024**3
            if device == "cuda" else None
        )

        result = {
            "model": model_name,
            "question": case["question"],
            "context": case["context"],
            "answer": answer,
            "generation_seconds": round(elapsed, 3),
            "peak_gpu_memory_gib": round(peak_gib, 3) if peak_gib is not None else None,
        }
        results.append(result)

        print(f"\nВопрос: {case['question']}")
        print(f"Ответ: {answer}")
        print(f"Время генерации: {elapsed:.2f} с")
        if peak_gib is not None:
            print(f"Пиковая память PyTorch: {peak_gib:.2f} ГиБ")
        print(flush=True)

    del model, tokenizer, inputs, output, generated
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

with open("generator_comparison.json", "w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)

print("Результаты сохранены: generator_comparison.json")
