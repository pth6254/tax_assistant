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

# ── Ollama ─────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL: str      = os.getenv("CHAT_MODEL",  "qwen3.5:35b-a3b")   # LLM
EMBED_MODEL: str     = os.getenv("EMBED_MODEL", "qwen3-embedding:4b") # 임베딩

# ── RAG 파라미터 ────────────────────────────────────────────────
CHUNK_SIZE: int    = 800
CHUNK_OVERLAP: int = 100
TOP_K: int         = 10
MEMORY_TURNS: int  = 3   # 채팅 메모리 최근 N 턴

# ── 임베딩 차원 ─────────────────────────────────────────────────
# qwen3-embedding:4b = 2560차원 → init_db.sql도 함께 수정 필요
EMBED_DIM: int = 2560

# ── JWT ────────────────────────────────────────────────────────
JWT_SECRET: str     = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
JWT_ALGORITHM: str  = "HS256"
JWT_EXPIRE_MIN: int = int(os.getenv("JWT_EXPIRE_MIN", "1440"))  # 기본 24시간

# ── Tavily ─────────────────────────────────────────────────────
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")