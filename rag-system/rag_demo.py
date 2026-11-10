from pathlib import Path

import chromadb
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "vector-db-lab" / "chroma_db"

EMBEDDING_MODEL = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)
LLM_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

if not DB_PATH.is_dir():
    raise FileNotFoundError(f"База ChromaDB не найдена: {DB_PATH}")

if not torch.cuda.is_available():
    raise RuntimeError("CUDA недоступна. Проверь PyTorch и видеокарту.")

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_collection(name="learning_materials_ru")

if collection.count() == 0:
    raise RuntimeError("Коллекция не содержит документов.")

print("Загрузка модели эмбеддингов на CPU...")
embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")

print("Загрузка Qwen на GPU...")
tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL)
model = AutoModelForCausalLM.from_pretrained(
    LLM_MODEL,
    dtype=torch.float16,
).to("cuda")
model.eval()

print("Модели загружены.")
print(f"Документов в коллекции: {collection.count()}")

def retrieve(question, top_k=3):
    embedding = embedder.encode(
        [question],
        convert_to_numpy=True,
    ).tolist()

    results = collection.query(
        query_embeddings=embedding,
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    return [
        {
            "id": doc_id,
            "text": text,
            "category": metadata.get("category", ""),
            "distance": float(distance),
        }
        for doc_id, text, metadata, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]

def answer_question(question):
    documents = retrieve(question)

    context = "\n".join(
        f"[{doc['id']}] {doc['text']}"
        for doc in documents
    )

    instruction = (
        "Отвечай на русском языке, используя только информацию из контекста. "
        "Не используй собственные знания. Если контекст не содержит ответа "
        "на вопрос, напиши ровно: «Недостаточно данных для ответа»."
    )

    messages = [
        {"role": "system", "content": instruction},
        {
            "role": "user",
            "content": f"Контекст:\n{context}\n\nВопрос: {question}",
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
    answer = tokenizer.decode(generated, skip_special_tokens=True)

    print("\n" + "=" * 60)
    print("Вопрос:", question)
    print("\nОтвет модели:")
    print(answer.strip())

    print("\nНайденные фрагменты:")
    for doc in documents:
        print(
            f"- [{doc['id']}] {doc['text']} "
            f"(расстояние: {doc['distance']:.4f})"
        )

questions = [
    "Как подобрать задания с учётом уровня студента?",
    "Как оценить качество обученной модели?",
    "Какой язык программирования лучше всего изучать?",
]

for question in questions:
    answer_question(question)

print("\nПроверка RAG-прототипа завершена.")
