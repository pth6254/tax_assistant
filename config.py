"""
config.py — 환경변수 중앙 관리
모든 설정값은 여기서만 읽어서, 다른 모듈은 이 파일만 import합니다.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ── DB ─────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/tax_db",
)

# ── 생성 LLM (Ollama, llama.cpp 또는 OpenRouter) ───────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_BASE_URL: str = os.getenv(
    "LLM_BASE_URL",
    "https://openrouter.ai/api/v1" if LLM_PROVIDER == "openrouter" else
    "https://api.openai.com/v1" if LLM_PROVIDER == "openai" else "http://localhost:8000/v1",
)
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "local-llamacpp")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LLM_TIMEOUT_SEC: float = float(os.getenv("LLM_TIMEOUT_SEC", "180"))
# Paid/remote providers always have an output budget (including reasoning tokens).
LLM_REMOTE_MAX_TOKENS: int = int(os.getenv("LLM_REMOTE_MAX_TOKENS", "8192"))
if LLM_REMOTE_MAX_TOKENS <= 0:
    raise ValueError("LLM_REMOTE_MAX_TOKENS must be positive")
LLM_MAX_CONTINUATIONS: int = int(os.getenv("LLM_MAX_CONTINUATIONS", "2"))
if not 0 <= LLM_MAX_CONTINUATIONS <= 4:
    raise ValueError("LLM_MAX_CONTINUATIONS must be between 0 and 4")
LLM_DEVICE: str = os.getenv("LLM_DEVICE", "auto").lower()

# ── Ollama (임베딩 및 기존 생성 LLM 호환) ─────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL: str      = os.getenv("CHAT_MODEL",  "qwen3.5:9b")          # LLM
LLM_TASK_NAMES = (
    "answer", "history_answer", "citation_extraction", "query_classification",
    "tool_selection", "document_classification",
)
_DEFAULT_EFFORT = {
    "answer": "low", "history_answer": "low", "citation_extraction": "low",
    "query_classification": "low", "tool_selection": "low", "document_classification": "none",
}
_VALID_EFFORT = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


@dataclass(frozen=True)
class LLMTaskSettings:
    provider: str
    model: str
    base_url: str
    timeout_sec: float
    reasoning_effort: str | None
    think_enabled: bool
    temperature: float | None
    max_tokens: int | None
    api_key: str = field(repr=False)


def _task_settings(name: str) -> LLMTaskSettings:
    prefix = f"LLM_TASK_{name.upper()}_"
    provider = os.getenv(prefix + "PROVIDER", LLM_PROVIDER).lower()
    if provider not in {"ollama", "llamacpp", "openai", "openai-compatible", "openrouter"}:
        raise ValueError(f"Unsupported {prefix}PROVIDER: {provider}")
    model = os.getenv(prefix + "MODEL", CHAT_MODEL)
    default_url = OLLAMA_BASE_URL if provider == "ollama" else (
        LLM_BASE_URL if provider == LLM_PROVIDER else
        "https://openrouter.ai/api/v1" if provider == "openrouter" else
        "https://api.openai.com/v1" if provider == "openai" else "http://localhost:8000/v1"
    )
    base_url = os.getenv(prefix + "BASE_URL", default_url)
    default_key = (OPENROUTER_API_KEY if provider == "openrouter" else
                   OPENAI_API_KEY if provider == "openai" else LLM_API_KEY)
    effort_default = (
        _DEFAULT_EFFORT[name] if model in {"openai/gpt-6-luna", "gpt-6-luna"} else
        "minimal" if model in {"openai/gpt-5-nano", "gpt-5-nano"} else ""
    )
    effort = os.getenv(prefix + "REASONING_EFFORT", effort_default).lower() or None
    if effort is not None and effort not in _VALID_EFFORT:
        raise ValueError(f"Unsupported {prefix}REASONING_EFFORT: {effort}")
    timeout = float(os.getenv(prefix + "TIMEOUT_SEC", str(LLM_TIMEOUT_SEC)))
    max_tokens_raw = os.getenv(prefix + "MAX_TOKENS", "")
    max_tokens = int(max_tokens_raw) if max_tokens_raw else None
    temperature_raw = os.getenv(prefix + "TEMPERATURE", "")
    temperature = float(temperature_raw) if temperature_raw else None
    if timeout <= 0 or (max_tokens is not None and max_tokens <= 0):
        raise ValueError(f"{prefix}TIMEOUT_SEC and MAX_TOKENS must be positive")
    return LLMTaskSettings(
        provider=provider, model=model, base_url=base_url, timeout_sec=timeout,
        reasoning_effort=effort,
        think_enabled=os.getenv(prefix + "THINK_ENABLED", str(THINK_ENABLED)).lower() == "true",
        temperature=temperature, max_tokens=max_tokens,
        api_key=os.getenv(prefix + "API_KEY", default_key),
    )


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

# Call sites select a fixed task name; arbitrary request input cannot choose a provider.
LLM_TASK_SETTINGS: dict[str, LLMTaskSettings] = {name: _task_settings(name) for name in LLM_TASK_NAMES}


@dataclass(frozen=True)
class KGJudgeSettings:
    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    reasoning_effort: str | None = None
    timeout_sec: float = 120
    max_tokens: int = 512
    input_budget_bytes: int = 6000
    num_ctx: int = 8192


def _kg_judge_settings() -> KGJudgeSettings:
    provider = os.getenv('KG_JUDGE_PROVIDER', LLM_PROVIDER).lower()
    if provider not in {'ollama', 'llamacpp', 'openai', 'openai-compatible', 'openrouter'}:
        raise ValueError('Unsupported KG_JUDGE_PROVIDER')
    default_url = (OLLAMA_BASE_URL if provider == 'ollama' else
                   LLM_BASE_URL if provider == LLM_PROVIDER else
                   'https://openrouter.ai/api/v1' if provider == 'openrouter' else
                   'https://api.openai.com/v1' if provider == 'openai' else
                   'http://localhost:8000/v1')
    default_key = (OPENROUTER_API_KEY if provider == 'openrouter' else
                   OPENAI_API_KEY if provider == 'openai' else LLM_API_KEY)
    effort = os.getenv('KG_JUDGE_REASONING_EFFORT', '').lower() or None
    if effort is not None and effort not in _VALID_EFFORT:
        raise ValueError('Unsupported KG_JUDGE_REASONING_EFFORT')
    settings = KGJudgeSettings(
        provider=provider, model=os.getenv('KG_JUDGE_MODEL', CHAT_MODEL),
        base_url=os.getenv('KG_JUDGE_BASE_URL', default_url),
        api_key=os.getenv('KG_JUDGE_API_KEY') or default_key,
        reasoning_effort=effort,
        timeout_sec=float(os.getenv('KG_JUDGE_TIMEOUT_SEC', '120')),
        max_tokens=int(os.getenv('KG_JUDGE_MAX_TOKENS', '512')),
        input_budget_bytes=int(os.getenv('KG_JUDGE_INPUT_BUDGET_BYTES', '6000')),
        num_ctx=int(os.getenv('KG_JUDGE_NUM_CTX', '8192')),
    )
    if min(settings.timeout_sec, settings.max_tokens,
           settings.input_budget_bytes, settings.num_ctx) <= 0:
        raise ValueError('KG_JUDGE limits must be positive')
    return settings


KG_JUDGE_SETTINGS: KGJudgeSettings = _kg_judge_settings()

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
GRAPH_RAG_ENABLED: bool = os.getenv("GRAPH_RAG_ENABLED", "false").lower() == "true"
HISTORY_GRAPH_RAG_ENABLED: bool = os.getenv("HISTORY_GRAPH_RAG_ENABLED", "false").lower() == "true"
GRAPH_TIMEOUT_SEC: float = float(os.getenv("GRAPH_TIMEOUT_SEC", "3"))
NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")
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
