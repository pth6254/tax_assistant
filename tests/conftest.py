"""
conftest.py — pytest 공통 픽스처

환경변수는 앱 모듈 import 전에 반드시 설정해야 한다.
(config.py가 import 시점에 JWT_SECRET 유무를 검사하기 때문)
"""
import os

import dotenv

# Unit tests see the same settings on every machine. The developer's .env (real database,
# paid model keys) is never loaded, so a test passes here only if it passes in CI.
dotenv.load_dotenv = lambda *args, **kwargs: False
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only")
# API tests run against a mocked connection; daily limits have their own tests (test_usage_limits.py).
os.environ["CHAT_DAILY_LIMIT_PER_USER"] = "0"
os.environ["CHAT_DAILY_LIMIT_TOTAL"] = "0"
os.environ["SIGNUP_INVITE_CODE"] = ""
# Nothing listens on port 1: an unmocked database access fails at once instead of
# silently reading the development database.
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@127.0.0.1:1/unit_tests_have_no_database"
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("LAW_API_KEY", "test-law-api-key")
os.environ.setdefault("TAVILY_API_KEY", "")
# Unit tests must never send synthetic prompts to a real tracing account.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


def pytest_addoption(parser):
    parser.addoption('--run-neo4j', action='store_true', help='Run isolated Docker Neo4j tests')
    parser.addoption('--graph-real-sample', action='store_true', help='Also read public law sample from tax_backend; requires --run-neo4j')


def _make_mock_pool() -> tuple:
    """asyncpg Pool 동작을 흉내내는 목 객체 생성."""
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.fixture(scope="session")
def mock_pool():
    return _make_mock_pool()


@pytest.fixture(scope="session")
def client(mock_pool):
    """DB 연결 없이 FastAPI 앱을 실행하는 테스트 클라이언트."""
    from unittest.mock import patch

    pool, _ = mock_pool
    with patch("app.database.get_pool", AsyncMock(return_value=pool)):
        from main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_cookie(client) -> dict:
    """유효한 JWT 쿠키가 담긴 딕셔너리 반환 (인증 필요 엔드포인트 테스트용)."""
    from app.core.security import create_access_token
    import uuid

    token = create_access_token(str(uuid.uuid4()), "test@example.com")
    return {"access_token": token}
