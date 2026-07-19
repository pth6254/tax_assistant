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
    settings.get("CHAT_MODEL", "qwen3.5:9b"),
    settings.get("EMBED_MODEL", "qwen3-embedding:4b"),
]
rerank_model = settings.get("RERANK_MODEL", "")
if rerank_model:
    required.append(rerank_model)

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

docker compose up -d --build "$@"

echo
echo "[OK] Docker Compose 실행 완료"
docker compose ps
