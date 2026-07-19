"""Service liveness, readiness, and external dependency diagnostics."""
import logging

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import get_pool
from app.utils.embeddings import get_http_client
from config import CHAT_MODEL, EMBED_MODEL, OLLAMA_BASE_URL, RERANK_MODEL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


async def _database_status() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        revision = await conn.fetchval("SELECT version_num FROM alembic_version LIMIT 1")
    return {
        "status": "ok",
        "version": version[:60],
        "alembic_revision": revision,
    }


async def _ollama_status() -> dict:
    required = [CHAT_MODEL, EMBED_MODEL]
    if RERANK_MODEL:
        required.append(RERANK_MODEL)

    try:
        response = await get_http_client().get(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags",
            timeout=3.0,
        )
        response.raise_for_status()
        available = {
            model.get("name", "")
            for model in response.json().get("models", [])
            if model.get("name")
        }
        missing = [model for model in required if model not in available]
        return {
            "status": "ok" if not missing else "model_missing",
            "connected": True,
            "required_models": required,
            "missing_models": missing,
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Ollama 상태 확인 실패: %s", exc)
        return {
            "status": "unreachable",
            "connected": False,
            "required_models": required,
            "missing_models": required,
        }


@router.get("/live")
async def liveness():
    """Process-only probe. It deliberately avoids external dependencies."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness():
    """Docker readiness probe: API, DB, and migrated schema must be available."""
    try:
        database = await _database_status()
    except Exception:
        logger.exception("DB readiness 확인 실패")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": {"status": "unavailable"}},
        )
    return {"status": "ready", "database": database}


@router.get("/dependencies")
async def dependencies():
    """Detailed status for UI/operations; Ollama degradation does not kill the API."""
    try:
        database = await _database_status()
    except Exception:
        logger.exception("DB dependency 확인 실패")
        database = {"status": "unavailable"}

    ollama = await _ollama_status()
    ready = database["status"] == "ok" and ollama["status"] == "ok"
    return {
        "status": "ready" if ready else "degraded",
        "database": database,
        "ollama": ollama,
    }


@router.get("")
async def legacy_health():
    """Backward-compatible DB health endpoint used by existing clients."""
    try:
        database = await _database_status()
    except Exception:
        logger.exception("레거시 health 확인 실패")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "db": "unavailable"},
        )
    return {
        "status": "ok",
        "db": database["version"],
        "alembic_revision": database["alembic_revision"],
    }
