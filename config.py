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

# ── 생성 LLM (Ollama 또는 llama.cpp OpenAI 호환 서버) ─────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "local-llamacpp")
LLM_TIMEOUT_SEC: float = float(os.getenv("LLM_TIMEOUT_SEC", "180"))
LLM_DEVICE: str = os.getenv("LLM_DEVICE", "auto").lower()

# ── Ollama (임베딩 및 기존 생성 LLM 호환) ─────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL: str      = os.getenv("CHAT_MODEL",  "qwen3.5:9b")          # LLM
EMBED_MODEL: str     = os.getenv("EMBED_MODEL", "qwen3-embedding:4b")  # 임베딩
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", OLLAMA_BASE_URL)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", EMBED_MODEL)
EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "auto").lower()
EMBEDDING_TIMEOUT_SEC: float = float(os.getenv("EMBEDDING_TIMEOUT_SEC", "300"))
EMBEDDING_VERSION: str = os.getenv("EMBEDDING_VERSION", "v1").lower()
EMBEDDING_DUAL_WRITE: bool = os.getenv("EMBEDDING_DUAL_WRITE", "false").lower() == "true"
EMBEDDING_V1_PROVIDER: str = os.getenv("EMBEDDING_V1_PROVIDER", "ollama").lower()
EMBEDDING_V1_BASE_URL: str = os.getenv("EMBEDDING_V1_BASE_URL", OLLAMA_BASE_URL)
EMBEDDING_V1_MODEL: str = os.getenv("EMBEDDING_V1_MODEL", EMBED_MODEL)
EMBEDDING_V2_PROVIDER: str = os.getenv("EMBEDDING_V2_PROVIDER", "llamacpp").lower()
EMBEDDING_V2_BASE_URL: str = os.getenv("EMBEDDING_V2_BASE_URL", "http://llama_embedding:8080/v1")
EMBEDDING_V2_MODEL: str = os.getenv("EMBEDDING_V2_MODEL", "qwen3-embedding:4b-gguf")
THINK_ENABLED: bool  = os.getenv("THINK_ENABLED", "false").lower() == "true"  # 기본 비활성화

# 모든 chat 모델 호출에서 동일한 num_ctx를 사용해야 함 — 값이 다르면
# Ollama가 요청마다 모델을 리로드하여 호출당 4~10초가 추가됨
OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
# 유휴 시 모델 언로드 금지 (-1) — 5분 유휴 후 콜드 스타트(27~48초) 방지
OLLAMA_KEEP_ALIVE: int = int(os.getenv("OLLAMA_KEEP_ALIVE_SEC", "-1"))

# ── RAG 파라미터 ────────────────────────────────────────────────
CHUNK_SIZE: int         = 800
CHUNK_OVERLAP: int      = 100
TOP_K: int              = 5
MEMORY_TURNS: int       = 3     # 채팅 메모리 최근 N 턴
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.4"))

# ── 업로드 제한 ─────────────────────────────────────────────────
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "50"))  # PDF 최대 크기 (MB)

# ── 임베딩 차원 ─────────────────────────────────────────────────
# qwen3-embedding:4b = 2560차원 → init_db.sql도 함께 수정 필요
EMBED_DIM: int = 2560

if EMBEDDING_VERSION not in {"v1", "v2"}:
    raise ValueError("EMBEDDING_VERSION must be either 'v1' or 'v2'")
for name, value in {
    "EMBEDDING_PROVIDER": EMBEDDING_PROVIDER,
    "EMBEDDING_V1_PROVIDER": EMBEDDING_V1_PROVIDER,
    "EMBEDDING_V2_PROVIDER": EMBEDDING_V2_PROVIDER,
}.items():
    if value not in {"ollama", "llamacpp"}:
        raise ValueError(f"{name} must be either 'ollama' or 'llamacpp'")
for name, value in {
    "LLM_DEVICE": LLM_DEVICE,
    "EMBEDDING_DEVICE": EMBEDDING_DEVICE,
}.items():
    if value not in {"auto", "cpu", "gpu"}:
        raise ValueError(f"{name} must be one of 'auto', 'cpu', or 'gpu'")

# ── 쿠키 보안 ───────────────────────────────────────────────────
COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# ── JWT ────────────────────────────────────────────────────────
JWT_SECRET: str     = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
JWT_ALGORITHM: str  = "HS256"
JWT_EXPIRE_MIN: int = int(os.getenv("JWT_EXPIRE_MIN", "1440"))  # 기본 24시간

# ── Tavily ─────────────────────────────────────────────────────
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# ── 국가법령정보 Open API ────────────────────────────────────────
# 발급: https://www.law.go.kr/LSO/openApi/openApiIntroPage.do
LAW_API_KEY: str = os.getenv("LAW_API_KEY", "")
