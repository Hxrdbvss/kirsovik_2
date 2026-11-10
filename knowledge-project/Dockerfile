FROM python:3.10-slim

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "torch==2.11.0+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements-docker.txt /app/requirements-docker.txt
RUN python -m pip install --no-cache-dir -r /app/requirements-docker.txt

COPY catalog_api.py /app/catalog_api.py

ENV HF_HOME=/model-cache
ENV HF_HUB_OFFLINE=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "catalog_api:app", "--host", "0.0.0.0", "--port", "8000"]
