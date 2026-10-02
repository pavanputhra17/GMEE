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

EXPOSE 8000

# Production: no --reload, 2 workers for free tier, bind to PORT env var.
# JSON form (with sh -c) keeps BuildKit's JSONArgsRecommended check green
# while still expanding ${PORT:-8000} at container start.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]

