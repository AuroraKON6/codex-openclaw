#!/bin/sh
# Cross-platform entry for macOS and Linux. Windows keeps quant.ps1 and the
# other .ps1 scripts; see docs/macos-runbook.md.
set -eu
root="$(cd "$(dirname "$0")" && pwd)"
cd "$root"
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# bootstrap must work before .venv exists, so fall back to a base CPython 3.11.
if [ -x "$root/.venv/bin/python" ]; then
    base="$root/.venv/bin/python"
else
    base="${QUANT_BASE_PYTHON:-}"
    if [ -z "$base" ]; then
        if command -v python3.11 >/dev/null 2>&1; then base="python3.11"; else base="python3"; fi
    fi
fi
exec "$base" "$root/tools/quant_ops.py" "$@"
