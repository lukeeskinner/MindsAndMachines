#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv_cmd="$1"
if [ ! -x "$uv_cmd" ]; then
  python3 -m venv .tools
  .tools/bin/python -m pip install uv==0.8.22
fi
"$uv_cmd" sync --project backend --locked
npm --prefix frontend ci
