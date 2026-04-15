"""
config.py — 환경변수 중앙 관리
모든 설정값은 여기서만 읽어서, 다른 모듈은 이 파일만 import합니다.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── DB ─────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/tax_db",
)

# ── OpenAI ─────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL: str    = "text-embedding-3-small"   # 1536차원
CHAT_MODEL: str     = "gpt-4o-mini"

# ── RAG 파라미터 ────────────────────────────────────────────────
CHUNK_SIZE: int    = 800
CHUNK_OVERLAP: int = 100
TOP_K: int         = 10
MEMORY_TURNS: int  = 3   # 채팅 메모리 최근 N 턴

# ── JWT ────────────────────────────────────────────────────────
# 반드시 .env 에서 교체: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET: str     = os.getenv("JWT_SECRET", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET")
JWT_ALGORITHM: str  = "HS256"
JWT_EXPIRE_MIN: int = int(os.getenv("JWT_EXPIRE_MIN", "1440"))  # 기본 24시간
