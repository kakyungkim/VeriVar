#!/usr/bin/env bash
# One-shot environment setup: create the Python 3.11 venv and install deps.
# Usage: ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3.11}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[!] $PY not found. Install Python 3.11 (e.g. 'brew install python@3.11') or set PYTHON=..."
  exit 1
fi

echo "[*] Creating venv with $($PY --version)"
"$PY" -m venv venv
./venv/bin/python -m pip install --quiet --upgrade pip wheel
echo "[*] Installing requirements (this pulls torch/chromadb — a few minutes)..."
./venv/bin/python -m pip install -r requirements.txt

echo "[*] Verifying..."
./venv/bin/python -c "import streamlit, chromadb, sentence_transformers, langchain_openai; print('  imports OK')"
./venv/bin/python -m pytest -q 2>&1 | tail -1

cat <<'EOF'

[+] Done. Next:
    - Put OPENAI_API_KEY in .env  (for Mode A LLM + dashboard chat)
    - Run analysis : ./venv/bin/python -m src.pipeline
    - Open dashboard: ./run_dashboard.sh
EOF
