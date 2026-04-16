#!/bin/sh
set -e

echo "Running DB table creation..."
python - <<'EOF'
import asyncio
from saras.db.postgres import engine
from saras.db.models import Base  # noqa: F401 — registers all models

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(init_db())
print("DB tables ready.")
EOF

echo "Running DB migrations..."
alembic upgrade head
echo "Migrations applied."

echo "Starting Saras API..."
exec uvicorn saras.main:app --host 0.0.0.0 --port 8000
