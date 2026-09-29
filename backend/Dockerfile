FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -e . && \
    python -m spacy download en_core_web_sm

RUN chmod +x start.sh

EXPOSE 8000

# Production: run migrations then start uvicorn
CMD ["./start.sh"]

