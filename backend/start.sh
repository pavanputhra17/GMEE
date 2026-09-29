#!/bin/bash
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head || echo "WARNING: Alembic migrations failed (may be first deploy)"

echo "==> Starting GMEE backend..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
