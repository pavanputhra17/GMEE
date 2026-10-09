FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY alembic ./alembic
COPY scripts ./scripts
RUN python -m pip install --upgrade pip && \
    python -m pip install -e . && \
    python -m spacy download en_core_web_sm

# Tests run in a Python image with dev dependencies, never in the runtime SPA.
FROM base AS test
RUN python -m pip install '.[dev]'
COPY tests ./tests
CMD ["pytest", "-m", "not integration", "--strict-markers"]

FROM base AS production
RUN useradd --create-home --uid 10001 gmee && \
    mkdir -p /home/gmee/.cache && \
    chown -R gmee:gmee /app /home/gmee
USER gmee
ENV HOME=/home/gmee
EXPOSE 8000

# Fail closed on migration errors; one worker avoids duplicate ML weights.
# Uvicorn trusts only an explicitly configured proxy peer (loopback by default).
COPY gmee_articles_export.csv ./
CMD ["sh", "-c", "alembic upgrade head && python scripts/import_articles.py gmee_articles_export.csv || true && exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
