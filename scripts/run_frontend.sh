#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"

cd "$project_root/frontend"
if [[ ! -d node_modules ]]; then
  echo "Frontend dependencies are missing. Run ./scripts/setup_once.sh first." >&2
  exit 1
fi

exec npm run dev -- --port "${VEILGRAPH_FRONTEND_PORT:-5173}"
