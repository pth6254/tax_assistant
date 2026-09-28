#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${PROJECT_DIR}/venv-wsl/bin/activate"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
  echo "[ERROR] WSL 가상환경을 찾을 수 없습니다: ${VENV_ACTIVATE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"
cd "${PROJECT_DIR}"

# WSL2 NAT에서 기본 게이트웨이는 WSL이 바라보는 Windows 호스트 주소다.
OLLAMA_WINDOWS_IP="$(ip -4 route show default | awk 'NR == 1 { print $3 }')"
if [[ -z "${OLLAMA_WINDOWS_IP}" ]]; then
  echo "[ERROR] WSL에서 Windows 호스트 IP를 탐지하지 못했습니다." >&2
  exit 1
fi
export OLLAMA_WINDOWS_IP

OLLAMA_URL="http://${OLLAMA_WINDOWS_IP}:11434"
TAGS_FILE="$(mktemp)"
trap 'rm -f "${TAGS_FILE}"' EXIT

echo "[INFO] Windows/Ollama 호스트 자동 탐지: ${OLLAMA_WINDOWS_IP}"

if ! curl -fsS --connect-timeout 3 --max-time 10 \
  "${OLLAMA_URL}/api/tags" >"${TAGS_FILE}"; then
  echo "[ERROR] Ollama에 연결할 수 없습니다: ${OLLAMA_URL}" >&2
  echo "[INFO] Windows Ollama 실행 상태와 OLLAMA_HOST 바인딩을 확인하세요." >&2
  exit 1
fi

# .env의 모델 설정과 Ollama가 실제 보유한 모델을 함께 검증한다.
python - "${TAGS_FILE}" <<'PY'
import json
import sys

from dotenv import dotenv_values
from config import LLM_TASK_SETTINGS

tags_path = sys.argv[1]
settings = dotenv_values(".env")

with open(tags_path, encoding="utf-8") as file:
    payload = json.load(file)

available = {
    model.get("name", "")
    for model in payload.get("models", [])
    if model.get("name")
}
required = [
    settings.get("EMBED_MODEL", "qwen3-embedding:4b"),
]
required.extend(task.model for task in LLM_TASK_SETTINGS.values() if task.provider == "ollama")
rerank_model = settings.get("RERANK_MODEL", "")
if rerank_model:
    required.append(rerank_model)

required = list(dict.fromkeys(required))
missing = [model for model in required if model not in available]
if missing:
    print("[ERROR] Ollama 필수 모델이 없습니다:", file=sys.stderr)
    for model in missing:
        print(f"  - {model}", file=sys.stderr)
    print("[INFO] Windows에서 'ollama pull <모델명>'을 실행하세요.", file=sys.stderr)
    raise SystemExit(1)

print("[OK] Ollama 연결 및 필수 모델 확인 완료")
for model in required:
    print(f"  - {model}")
PY

# A targeted backend rebuild otherwise leaves an exited optional Neo4j
# container stopped, even while GraphRAG remains enabled in the backend.
STARTS_BACKEND=false
if [[ $# -eq 0 ]]; then
  STARTS_BACKEND=true
else
  for service in "$@"; do
    if [[ "$service" == "backend" ]]; then
      STARTS_BACKEND=true
      break
    fi
  done
fi
if [[ "$STARTS_BACKEND" == true ]] && python - <<'PY'
import os
from dotenv import dotenv_values

settings = dotenv_values('.env')
current = str(os.getenv('GRAPH_RAG_ENABLED', settings.get('GRAPH_RAG_ENABLED') or 'false')).lower() == 'true'
history = str(os.getenv('HISTORY_GRAPH_RAG_ENABLED', settings.get('HISTORY_GRAPH_RAG_ENABLED') or 'true')).lower() == 'true'
raise SystemExit(0 if current or history else 1)
PY
then
  echo "[INFO] GraphRAG 사용 설정 감지: Neo4j 준비 상태 확인"
  docker compose up -d --wait neo4j
fi

docker compose up -d --build "$@"

echo
echo "[OK] Docker Compose 실행 완료"
docker compose ps
