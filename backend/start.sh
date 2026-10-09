#!/bin/bash
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head || echo "WARNING: Alembic migrations failed (may be first deploy)"

echo "==> Seeding initial data if available..."
python scripts/import_articles.py ../dataaa/gmee_articles_export.csv || echo "WARNING: Data import failed"

echo "==> Starting GMEE backend..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
