# Build context is the repo root (see docker-compose.yml) because the backend
# imports the CLI's src/abl_agents package and reads data/knowledge_base/*.md.
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY src/ src/
COPY backend/ backend/
COPY data/knowledge_base/ data/knowledge_base/

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
