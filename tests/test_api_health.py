"""Health endpoint tests."""
from unittest.mock import AsyncMock, patch


def test_liveness_does_not_require_dependencies(client):
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_returns_database_and_revision(client, mock_pool):
    _, conn = mock_pool
    conn.fetchval.side_effect = ["PostgreSQL 17.0 on x86_64", "20260719_0001"]

    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"]["alembic_revision"] == "20260719_0001"
    conn.fetchval.side_effect = None


def test_readiness_returns_503_when_database_fails(client, mock_pool):
    _, conn = mock_pool
    conn.fetchval.side_effect = RuntimeError("database unavailable")

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    conn.fetchval.side_effect = None


def test_dependencies_reports_embedding_degradation_without_503(client, mock_pool):
    _, conn = mock_pool
    conn.fetchval.side_effect = ["PostgreSQL 17.0 on x86_64", "20260719_0001"]
    embedding = {
        "status": "unreachable",
        "provider": "llamacpp",
        "connected": False,
        "model": "Qwen/Qwen3-Embedding-4B",
    }
    llm = {"status": "ok"}

    with (
        patch("app.routers.health._embedding_status", AsyncMock(return_value=embedding)),
        patch("app.routers.health._llm_status", AsyncMock(return_value=llm)),
    ):
        response = client.get("/api/health/dependencies")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["embedding"]["connected"] is False
    conn.fetchval.side_effect = None
