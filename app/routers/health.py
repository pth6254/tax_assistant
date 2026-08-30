"""Service liveness, readiness, and external dependency diagnostics."""
import logging

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import get_pool
from app.services.embedding_service import get_embedding_provider
from config import (
    CHAT_MODEL,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    EMBEDDING_DEVICE,
    EMBEDDING_VERSION,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_PROVIDER,
    LLM_DEVICE,
    OLLAMA_BASE_URL,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["health"])


async def _database_status() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        revision = await conn.fetchval("SELECT version_num FROM alembic_version LIMIT 1")
    return {"status": "ok", "version": version[:60], "alembic_revision": revision}


async def _ollama_status(required: list[str]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
        response.raise_for_status()
        available = {
            model.get("name", "")
            for model in response.json().get("models", [])
            if model.get("name")
        }
        missing = [model for model in required if model not in available]
        return {
            "status": "ok" if not missing else "model_missing",
            "provider": "ollama",
            "connected": True,
            "required_models": required,
            "missing_models": missing,
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Ollama health check failed: %s", exc)
        return {
            "status": "unreachable",
            "provider": "ollama",
            "connected": False,
            "required_models": required,
            "missing_models": required,
        }


async def _llm_status() -> dict:
    if LLM_PROVIDER == "ollama":
        result = await _ollama_status([CHAT_MODEL])
        result.update({"model": CHAT_MODEL, "device": LLM_DEVICE})
        return result
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"{LLM_BASE_URL.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            )
        response.raise_for_status()
        models = {item.get("id") for item in response.json().get("data", [])}
        missing = [] if CHAT_MODEL in models else [CHAT_MODEL]
        return {
            "status": "ok" if not missing else "model_missing",
            "provider": LLM_PROVIDER,
            "device": LLM_DEVICE,
            "model": CHAT_MODEL,
            "connected": True,
            "required_models": [CHAT_MODEL],
            "missing_models": missing,
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("LLM health check failed: %s", exc)
        return {
            "status": "unreachable",
            "provider": LLM_PROVIDER,
            "device": LLM_DEVICE,
            "model": CHAT_MODEL,
            "connected": False,
            "required_models": [CHAT_MODEL],
            "missing_models": [CHAT_MODEL],
        }


async def _embedding_status() -> dict:
    try:
        details = await get_embedding_provider().health()
        available = details.get("model_available", True)
        return {
            "status": "ok" if available else "model_missing",
            "provider": EMBEDDING_PROVIDER,
            "device": EMBEDDING_DEVICE,
            "model": EMBEDDING_MODEL,
            "version": EMBEDDING_VERSION,
            "dimension": 2560,
            "connected": details.get("connected", True),
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Embedding health check failed: %s", exc)
        return {
            "status": "unreachable",
            "provider": EMBEDDING_PROVIDER,
            "device": EMBEDDING_DEVICE,
            "model": EMBEDDING_MODEL,
            "version": EMBEDDING_VERSION,
            "dimension": 2560,
            "connected": False,
        }


@router.get("/live")
async def liveness():
    return {"status": "alive"}


@router.get("/ready")
async def readiness():
    try:
        database = await _database_status()
    except Exception:
        logger.exception("DB readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": {"status": "unavailable"}},
        )
    return {"status": "ready", "database": database}


@router.get("/dependencies")
async def dependencies():
    try:
        database = await _database_status()
    except Exception:
        logger.exception("DB dependency check failed")
        database = {"status": "unavailable"}
    llm = await _llm_status()
    embedding = await _embedding_status()
    ready = (
        database["status"] == "ok"
        and llm["status"] == "ok"
        and embedding["status"] == "ok"
    )
    return {
        "status": "ready" if ready else "degraded",
        "database": database,
        "llm": llm,
        "embedding": embedding,
    }


@router.get("")
async def legacy_health():
    try:
        database = await _database_status()
    except Exception:
        logger.exception("Legacy health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "db": "unavailable"},
        )
    return {
        "status": "ok",
        "db": database["version"],
        "alembic_revision": database["alembic_revision"],
    }
