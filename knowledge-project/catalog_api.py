from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import chromadb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from sentence_transformers import SentenceTransformer

DB_PATH = Path(__file__).resolve().parent / "chroma_db"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

state = {}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    level: Literal["начальный", "продвинутый"] | None = None
    top_k: int = Field(default=3, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Запрос не должен состоять только из пробелов.")
        return value


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.is_dir():
        raise RuntimeError("Каталог не найден. Сначала запусти build_catalog.py.")

    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_collection(name="learning_catalog")

    print("Загрузка модели эмбеддингов на CPU...", flush=True)
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    state.update({
        "client": client,
        "collection": collection,
        "model": model,
    })

    print("Сервис каталога готов к работе.", flush=True)
    yield
    state.clear()


app = FastAPI(
    title="Поиск учебных материалов",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ready",
        "documents": state["collection"].count(),
        "embedding_device": "cpu",
    }


@app.post("/search")
def search(request: SearchRequest):
    collection = state["collection"]
    count = collection.count()

    if count == 0:
        raise HTTPException(status_code=503, detail="Каталог пуст.")

    embedding = state["model"].encode(
        [request.query],
        convert_to_numpy=True,
    ).tolist()

    query_args = {
        "query_embeddings": embedding,
        "n_results": min(request.top_k, count),
        "include": ["metadatas", "distances"],
    }

    if request.level is not None:
        query_args["where"] = {"level": request.level}

    found = collection.query(**query_args)

    results = [
        {
            "id": doc_id,
            "title": metadata.get("title", ""),
            "topic": metadata.get("topic", ""),
            "level": metadata.get("level", ""),
            "distance": float(distance),
        }
        for doc_id, metadata, distance in zip(
            found["ids"][0],
            found["metadatas"][0],
            found["distances"][0],
        )
    ]

    return {
        "query": request.query,
        "level": request.level,
        "results": results,
    }


@app.get("/materials/{material_id}/graph")
def material_graph(material_id: str):
    """Получить тему материала и её непосредственные предварительные темы."""
    import os

    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError, ServiceUnavailable

    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise HTTPException(
            status_code=503,
            detail="Не задана переменная NEO4J_PASSWORD.",
        )

    try:
        with GraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
            auth=("neo4j", password),
        ) as driver:
            with driver.session() as session:
                records = list(session.run(
                    """
                    MATCH (material:Material {id: $material_id})
                    OPTIONAL MATCH (topic:Topic)-[:HAS_MATERIAL]->(material)
                    OPTIONAL MATCH (prerequisite:Topic)-[:PREREQUISITE_FOR]->(topic)
                    RETURN material.id AS id,
                           material.title AS title,
                           topic.name AS topic,
                           collect(DISTINCT prerequisite.name) AS prerequisites
                    """,
                    material_id=material_id,
                ))

        if not records:
            raise HTTPException(
                status_code=404,
                detail="Материал не найден в графовой базе.",
            )

        return {
            "material_id": material_id,
            "topics": [dict(record) for record in records],
        }

    except (Neo4jError, ServiceUnavailable) as error:
        print(f"Ошибка Neo4j: {type(error).__name__}: {error}", flush=True)
        raise HTTPException(
            status_code=503,
            detail="Не удалось получить данные из Neo4j. Проверь сервер и журнал.",
        ) from error


@app.post("/search-with-graph")
def search_with_graph(request: SearchRequest):
    """Поиск материалов и получение их связей из Neo4j."""
    response = search(request)

    for material in response["results"]:
        try:
            graph = material_graph(material["id"])
            material["graph_topics"] = graph["topics"]
            material["graph_status"] = "ok"
        except HTTPException as error:
            material["graph_topics"] = []
            if error.status_code == 404:
                material["graph_status"] = "material_not_found"
            elif error.status_code == 503:
                material["graph_status"] = "unavailable"
            else:
                raise

    return response
