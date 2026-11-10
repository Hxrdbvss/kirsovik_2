# Запуск проекта

## Подготовка

Запустить Docker Desktop в Windows. Открыть три терминала PowerShell
и в каждом войти в Ubuntu:

    wsl -d ubuntu

## Терминал 1 — Neo4j и каталог

    docker start neo4j-coursework
    docker start knowledge-catalog

Проверить состояние:

    docker ps --filter name=neo4j-coursework
    docker ps --filter name=knowledge-catalog
    curl -sS http://127.0.0.1:8005/health
    echo
    curl -sS http://127.0.0.1:8005/materials/mat_03/graph
    echo

Если Neo4j ещё загружается, повторить запрос к графу через некоторое время.

## Терминал 2 — RAG API

    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate mlops-lab
    cd ~/adaptive-learning-project/rag-system
    python -m uvicorn rag_api:app --host 127.0.0.1 --port 8003

Дождаться сообщения Application startup complete и оставить терминал открытым.

## Терминал 3 — объединённый API

    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate mlops-lab
    cd ~/adaptive-learning-project/knowledge-project
    python -m uvicorn unified_api:app --host 127.0.0.1 --port 8006

Дождаться сообщения Application startup complete и оставить терминал открытым.

## Проверка

В первом терминале:

    curl -sS http://127.0.0.1:8003/health
    echo
    curl -sS http://127.0.0.1:8005/health
    echo

    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate mlops-lab
    cd ~/adaptive-learning-project/knowledge-project
    python test_unified_api.py

Документация API:

- RAG: http://127.0.0.1:8003/docs
- Каталог: http://127.0.0.1:8005/docs
- Объединённый API: http://127.0.0.1:8006/docs

В объединённом API:
- POST /ask — учебные фрагменты и опционально факты графа;
- POST /ask-manual — поиск и ответ по методичке.

Для передачи фактов графа в запросе /ask указать "use_graph": true.
В /ask-manual используются вопрос и найденные фрагменты методички.

## Остановка

В терминалах 2 и 3 нажать Ctrl+C.

При необходимости остановить контейнеры:

    docker stop knowledge-catalog
    docker stop neo4j-coursework
