from fastapi import APIRouter
from pydantic import BaseModel

from saras.db.postgres import engine
from saras.db.redis import get_redis

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: str
    postgres: str
    redis: str
    version: str = "0.1.0"


@router.get("", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    postgres_ok = False
    redis_ok = False

    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        postgres_ok = True
    except Exception:
        pass

    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        pass

    overall = "healthy" if postgres_ok and redis_ok else "degraded"
    return HealthStatus(
        status=overall,
        postgres="ok" if postgres_ok else "unavailable",
        redis="ok" if redis_ok else "unavailable",
    )
