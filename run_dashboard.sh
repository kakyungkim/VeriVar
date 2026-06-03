#!/usr/bin/env bash
# Launch the Streamlit dashboard using the project venv (no activation needed).
# Works from any shell/conda env. Usage: ./run_dashboard.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x "venv/bin/streamlit" ]; then
  echo "[!] venv not set up. Run ./setup.sh first."
  exit 1
fi
if [ ! -f "data/outputs/cohort_interpretation.json" ]; then
  echo "[!] No results yet — running the pipeline first (needs OPENAI_API_KEY in .env)..."
  ./venv/bin/python -m src.pipeline
fi

echo "[*] Starting dashboard at http://localhost:8501  (Ctrl-C to stop)"
exec ./venv/bin/streamlit run src/dashboard/app.py "$@"
