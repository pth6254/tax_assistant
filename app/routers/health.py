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
    LLM_TASK_SETTINGS,
    OLLAMA_BASE_URL,
    OPENAI_API_KEY,
    OPENROUTER_API_KEY,
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


async def _llm_status(provider: str | None = None, model: str | None = None,
                      base_url: str | None = None, api_key: str | None = None) -> dict:
    provider = provider or LLM_PROVIDER
    model = model or CHAT_MODEL
    base_url = base_url or LLM_BASE_URL
    api_key = api_key if api_key is not None else (
        OPENROUTER_API_KEY if provider == "openrouter" else
        OPENAI_API_KEY if provider == "openai" else LLM_API_KEY
    )
    if provider == "ollama":
        result = await _ollama_status([model])
        result.update({"model": model, "device": LLM_DEVICE})
        return result
    if provider in {"openrouter", "openai"} and not api_key:
        return {
            "status": "configuration_missing",
            "provider": provider,
            "device": "remote",
            "model": model,
            "connected": False,
            "required_models": [model],
            "missing_models": [],
        }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        response.raise_for_status()
        models = {item.get("id") for item in response.json().get("data", [])}
        missing = [] if model in models else [model]
        return {
            "status": "ok" if not missing else "model_missing",
            "provider": provider,
            "device": "remote" if provider == "openrouter" else LLM_DEVICE,
            "model": model,
            "connected": True,
            "required_models": [model],
            "missing_models": missing,
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("LLM health check failed: %s", exc)
        return {
            "status": "unreachable",
            "provider": provider,
            "device": "remote" if provider == "openrouter" else LLM_DEVICE,
            "model": model,
            "connected": False,
            "required_models": [model],
            "missing_models": [model],
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
    checked = {}
    llm_tasks = {}
    for name, settings in LLM_TASK_SETTINGS.items():
        key = (settings.provider, settings.model, settings.base_url, settings.api_key)
        if key not in checked:
            checked[key] = await _llm_status(settings.provider, settings.model,
                                              settings.base_url, settings.api_key)
        llm_tasks[name] = {
            **checked[key],
            "reasoning_effort": settings.reasoning_effort,
            "think_enabled": settings.think_enabled if settings.provider in {"ollama", "llamacpp"} else None,
        }
    llm = llm_tasks["answer"]
    routing_llm = llm_tasks["tool_selection"]
    embedding = await _embedding_status()
    ready = (
        database["status"] == "ok"
        and llm["status"] == "ok"
        and routing_llm["status"] == "ok"
        and all(status["status"] == "ok" for status in llm_tasks.values())
        and embedding["status"] == "ok"
    )
    return {
        "status": "ready" if ready else "degraded",
        "database": database,
        "llm": llm,
        "routing_llm": routing_llm,
        "llm_tasks": llm_tasks,
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
