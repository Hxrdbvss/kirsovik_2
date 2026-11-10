import json

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

with open("paraphrase_evaluation.json", encoding="utf-8") as file:
    saved = json.load(file)

# Берём все пять сохранённых вопросов и те же найденные фрагменты.
cases = saved["results"]

prompts = {
    "strict": (
        "Отвечай на русском языке, используя только информацию из контекста. "
        "Не используй собственные знания. Если контекст не содержит ответа "
        "на вопрос, напиши ровно: «Недостаточно данных для ответа»."
    ),
    "extract": (
        "Найди в контексте фрагмент, который помогает ответить на вопрос. "
        "Вопрос может быть перефразирован: учитывай совпадение смысла. "
        "Если подходящий фрагмент есть, приведи только его текст дословно, "
        "без номера и без дополнительных пояснений. "
        "Если ответа в контексте нет, напиши ровно: "
        "«Недостаточно данных для ответа»."
    ),
}

if not torch.cuda.is_available():
    raise SystemExit("CUDA недоступна. Проверь PyTorch и видеокарту.")

print("Загрузка модели на GPU...", flush=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    dtype=torch.float16,
).to("cuda")
model.eval()

results = []

for prompt_name, instruction in prompts.items():
    print(f"\n{'=' * 60}")
    print(f"Инструкция: {prompt_name}", flush=True)

    for case in cases:
        context = "\n".join(
            f"[{source['id']}] {source['text']}"
            for source in case["sources"]
        )

        messages = [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": (
                    f"Контекст:\n{context}\n\n"
                    f"Вопрос: {case['question']}"
                ),
            },
        ]

        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to("cuda")

        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=160,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = output[0, inputs["input_ids"].shape[1]:]
        answer = tokenizer.decode(
            generated, skip_special_tokens=True
        ).strip()

        results.append({
            "prompt": prompt_name,
            "instruction": instruction,
            "question": case["question"],
            "sources": case["sources"],
            "answer": answer,
        })

        print(f"\nВопрос: {case['question']}")
        print(f"Ответ: {answer}", flush=True)

with open("extraction_prompt_comparison.json", "w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)

print("\nРезультаты сохранены: extraction_prompt_comparison.json")
