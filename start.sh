#!/bin/bash
set -e
echo "Running database migrations..."
alembic upgrade add_mvp_user_columns_and_tables
echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT