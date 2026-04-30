"""
conftest.py — pytest 공통 픽스처

환경변수는 앱 모듈 import 전에 반드시 설정해야 한다.
(config.py가 import 시점에 JWT_SECRET 유무를 검사하기 때문)
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/tax_db")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("LAW_API_KEY", "test-law-api-key")
os.environ.setdefault("TAVILY_API_KEY", "")

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


def _make_mock_pool() -> tuple:
    """asyncpg Pool 동작을 흉내내는 목 객체 생성."""
    conn = AsyncMock()
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
    from app.utils.jwt import create_access_token
    import uuid

    token = create_access_token(str(uuid.uuid4()), "test@example.com")
    return {"access_token": token}
