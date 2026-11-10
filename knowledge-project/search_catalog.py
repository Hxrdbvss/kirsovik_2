import argparse
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "chroma_db"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

parser = argparse.ArgumentParser(
    description="Поиск учебных материалов в каталоге."
)
parser.add_argument("query", help="Поисковый запрос")
parser.add_argument(
    "--level",
    choices=["начальный", "продвинутый"],
    help="Уровень сложности материала",
)
parser.add_argument(
    "--top-k",
    type=int,
    default=3,
    help="Максимальное количество результатов",
)
args = parser.parse_args()

if not args.query.strip():
    parser.error("Запрос не должен быть пустым.")

if args.top_k < 1:
    parser.error("--top-k должен быть больше нуля.")

if not DB_PATH.is_dir():
    raise SystemExit("База не найдена. Сначала запусти build_catalog.py.")

client = chromadb.PersistentClient(path=str(DB_PATH))
collection = client.get_collection(name="learning_catalog")

if collection.count() == 0:
    raise SystemExit("Каталог пуст. Сначала запусти build_catalog.py.")

print("Загрузка модели эмбеддингов на CPU...", flush=True)
model = SentenceTransformer(MODEL_NAME, device="cpu")
query_embedding = model.encode(
    [args.query],
    convert_to_numpy=True,
).tolist()

query_args = {
    "query_embeddings": query_embedding,
    "n_results": min(args.top_k, collection.count()),
    "include": ["metadatas", "distances"],
}

if args.level:
    query_args["where"] = {"level": args.level}

result = collection.query(**query_args)
ids = result["ids"][0]

print(f"\nЗапрос: {args.query}")
print(f"Уровень: {args.level or 'любой'}")

if not ids:
    print("Материалы с указанным фильтром не найдены.")
else:
    for index, (doc_id, metadata, distance) in enumerate(
        zip(ids, result["metadatas"][0], result["distances"][0]),
        start=1,
    ):
        print(f"\n{index}. {metadata['title']}")
        print(f"   ID: {doc_id}")
        print(f"   Тема: {metadata['topic']}")
        print(f"   Уровень: {metadata['level']}")
        print(f"   Расстояние: {distance:.4f}")
