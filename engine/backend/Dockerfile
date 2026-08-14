# Two targets on purpose. `api` serves; `ingest` parses documents and pulls in
# torch, transformers and OpenCV — roughly ten times the image size for a stack
# the request path never imports.

FROM python:3.12-slim AS api

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.12-slim AS ingest

# libgl1/libglib2.0-0 are OpenCV's runtime dependencies, pulled in by easyocr.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-ingest.txt ./
RUN pip install --no-cache-dir -r requirements-ingest.txt

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "ingestion", "status"]
