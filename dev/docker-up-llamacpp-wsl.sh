#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${PROJECT_DIR}/venv-wsl/bin/activate"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
  echo "[ERROR] WSL virtual environment not found: ${VENV_ACTIVATE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"
cd "${PROJECT_DIR}"

export OLLAMA_WINDOWS_IP="$(ip -4 route show default | awk 'NR == 1 { print $3 }')"
if [[ -z "${OLLAMA_WINDOWS_IP}" ]]; then
  echo "[ERROR] Could not detect the Windows host IP." >&2
  exit 1
fi

if ! docker run --rm --gpus all --entrypoint nvidia-smi \
  ghcr.io/ggml-org/llama.cpp:server-cuda >/dev/null; then
  echo "[ERROR] Docker cannot access the NVIDIA GPU." >&2
  exit 1
fi

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
  echo "[INFO] GraphRAG enabled: waiting for Neo4j"
  docker compose -f docker-compose.yml -f docker-compose.llamacpp.yml up -d --wait neo4j
fi

docker compose -f docker-compose.yml -f docker-compose.llamacpp.yml up -d --build "$@"

echo
echo "[OK] llama.cpp Docker Compose stack started"
docker compose -f docker-compose.yml -f docker-compose.llamacpp.yml ps
