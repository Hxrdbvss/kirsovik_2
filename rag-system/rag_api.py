from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
import time

import chromadb
import torch
from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "vector-db-lab" / "chroma_db"

EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
LLM_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

INSTRUCTION = (
    "Отвечай на русском языке, используя только информацию из контекста. "
    "Не используй собственные знания. Если контекст не содержит ответа "
    "на вопрос, напиши ровно: «Недостаточно данных для ответа»."
)

state = {}
generation_lock = Lock()


class QuestionRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=1000,
        description="Вопрос к базе документов",
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Вопрос не должен быть пустым.")
        return value


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.is_dir():
        raise RuntimeError(f"База ChromaDB не найдена: {DB_PATH}")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA недоступна. Проверь PyTorch и видеокарту.")

    print("Подключение к ChromaDB...", flush=True)
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_collection(name="learning_materials_ru")

    if collection.count() == 0:
        raise RuntimeError("Коллекция не содержит документов.")

    print("Загрузка модели эмбеддингов на CPU...", flush=True)
    embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")

    print("Загрузка Qwen на GPU...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        LLM_MODEL,
        dtype=torch.float16,
    ).to("cuda")
    model.eval()

    state.update({
        "client": client,
        "collection": collection,
        "embedder": embedder,
        "tokenizer": tokenizer,
        "model": model,
    })

    print("RAG-сервис готов к работе.", flush=True)
    yield
    state.clear()


app = FastAPI(title="RAG-система для учебных материалов", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ready",
        "device": "cuda",
        "documents": state["collection"].count(),
        "model": LLM_MODEL,
    }


@app.post("/ask")
def ask(request: QuestionRequest):
    started = time.perf_counter()

    # Один запрос за раз, чтобы не переполнить видеопамять.
    with generation_lock:
        collection = state["collection"]
        embedding = state["embedder"].encode(
            [request.question],
            convert_to_numpy=True,
        ).tolist()

        found = collection.query(
            query_embeddings=embedding,
            n_results=min(3, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = [
            {
                "id": doc_id,
                "text": text,
                "category": (metadata or {}).get("category", ""),
                "distance": float(distance),
            }
            for doc_id, text, metadata, distance in zip(
                found["ids"][0],
                found["documents"][0],
                found["metadatas"][0],
                found["distances"][0],
            )
        ]

        context = "\n".join(
            f"[{doc['id']}] {doc['text']}"
            for doc in documents
        )

        messages = [
            {"role": "system", "content": INSTRUCTION},
            {
                "role": "user",
                "content": (
                    f"Контекст:\n{context}\n\n"
                    f"Вопрос: {request.question}"
                ),
            },
        ]

        tokenizer = state["tokenizer"]
        model = state["model"]

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
            generated,
            skip_special_tokens=True,
        ).strip()

    return {
        "question": request.question,
        "answer": answer,
        "sources": documents,
        "processing_time_seconds": round(time.perf_counter() - started, 3),
    }


class GraphQuestionRequest(QuestionRequest):
    graph_facts: list[str] = Field(default_factory=list, max_length=10)


@app.post("/ask-with-graph")
def ask_with_graph(request: GraphQuestionRequest):
    """Ответ по найденным фрагментам и переданным сведениям графа."""
    started = time.perf_counter()

    with generation_lock:
        collection = state["collection"]
        embedding = state["embedder"].encode(
            [request.question],
            convert_to_numpy=True,
        ).tolist()

        found = collection.query(
            query_embeddings=embedding,
            n_results=min(3, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = [
            {
                "id": doc_id,
                "text": text,
                "category": (metadata or {}).get("category", ""),
                "distance": float(distance),
            }
            for doc_id, text, metadata, distance in zip(
                found["ids"][0],
                found["documents"][0],
                found["metadatas"][0],
                found["distances"][0],
            )
        ]

        fragments = "\n".join(
            f"[{doc['id']}] {doc['text']}"
            for doc in documents
        )
        graph_context = "\n".join(
            f"- {fact}" for fact in request.graph_facts
        ) or "Нет сведений из графа."

        messages = [
            {"role": "system", "content": INSTRUCTION},
            {
                "role": "user",
                "content": (
                    f"Фрагменты документов:\n{fragments}\n\n"
                    f"Сведения из графа:\n{graph_context}\n\n"
                    f"Вопрос: {request.question}"
                ),
            },
        ]

        tokenizer = state["tokenizer"]
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to("cuda")

        with torch.inference_mode():
            output = state["model"].generate(
                **inputs,
                max_new_tokens=160,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = output[0, inputs["input_ids"].shape[1]:]
        answer = tokenizer.decode(
            generated, skip_special_tokens=True
        ).strip()

    return {
        "question": request.question,
        "answer": answer,
        "sources": documents,
        "graph_facts": request.graph_facts,
        "processing_time_seconds": round(time.perf_counter() - started, 3),
    }


@app.post("/ask-manual")
def ask_manual(request: QuestionRequest):
    """Ответ по фрагментам методички с указанием страниц PDF."""
    started = time.perf_counter()
    manual_db_path = Path(__file__).resolve().parent / "manual_chroma_db"

    if not manual_db_path.is_dir():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="База методички не найдена. Сначала выполни index_lab_manual.py.",
        )

    with generation_lock:
        from fastapi import HTTPException

        try:
            client = chromadb.PersistentClient(path=str(manual_db_path))
            collection = client.get_collection(name="lab_manual")
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=f"Не удалось открыть коллекцию методички: {error}",
            ) from error

        count = collection.count()
        if count == 0:
            raise HTTPException(
                status_code=503,
                detail="Коллекция методички пуста.",
            )

        embedding = state["embedder"].encode(
            [request.question],
            convert_to_numpy=True,
        ).tolist()

        found = collection.query(
            query_embeddings=embedding,
            n_results=min(3, count),
            include=["documents", "metadatas", "distances"],
        )

        documents = [
            {
                "id": doc_id,
                "text": text,
                "source": (metadata or {}).get("source", ""),
                "page": (metadata or {}).get("page"),
                "distance": float(distance),
            }
            for doc_id, text, metadata, distance in zip(
                found["ids"][0],
                found["documents"][0],
                found["metadatas"][0],
                found["distances"][0],
            )
        ]

        context = "\n\n".join(
            f"[{doc['id']}, страница PDF {doc['page']}]\n{doc['text']}"
            for doc in documents
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Ответь на русском языке кратко, в двух-трёх предложениях. "
                    "Используй только сведения из приведённых фрагментов. "
                    "Не добавляй примеры и не перечисляй то, о чём не спрашивали. "
                    "Не обобщай частные случаи. "
                    "Если ответа в фрагментах нет, напиши ровно: "
                    "«Недостаточно данных для ответа»."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Фрагменты методички:\n{context}\n\n"
                    f"Вопрос: {request.question}"
                ),
            },
        ]

        tokenizer = state["tokenizer"]
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to("cuda")

        with torch.inference_mode():
            output = state["model"].generate(
                **inputs,
                max_new_tokens=160,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = output[0, inputs["input_ids"].shape[1]:]
        answer = tokenizer.decode(
            generated,
            skip_special_tokens=True,
        ).strip()

    return {
        "question": request.question,
        "answer": answer,
        "sources": documents,
        "processing_time_seconds": round(time.perf_counter() - started, 3),
    }
