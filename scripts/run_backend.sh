#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"

cd "$project_root/backend"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Backend environment is missing. Run ./scripts/setup_once.sh first." >&2
  exit 1
fi

export PYTHONPATH=.
exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port "${VEILGRAPH_BIND_PORT:-8000}"
