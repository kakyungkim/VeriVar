#!/usr/bin/env bash
# Cross-engine manuscript verification with codex (a DIFFERENT model/harness).
#
# Why a second engine: re-running the SAME model as a "critic" does not reliably
# catch that model's own hallucinations — it shares the failure mode. A different
# engine has different hallucination patterns, so it tends to flag values the
# first engine invented. We use codex for what it is reliable at: DETERMINISTIC,
# checkable cross-referencing (does prose match JSON? do DOIs resolve?), NOT for
# variant-biology judgement (which both engines can hallucinate — that needs a
# human molecular pathologist).
#
# Pipeline:
#   1. Run the deterministic Python verifier first (ground truth, no LLM).
#   2. Hand codex the SAME task in read-only mode, told to defer to the JSON and
#      to the Python verifier, and to report ONLY discrepancies it can cite.
#
# Usage:
#   bash scripts/verify_with_codex.sh             # python verifier + codex cross-check
#   bash scripts/verify_with_codex.sh --no-codex  # python verifier only
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==================================================================="
echo " STEP 1/2 — deterministic Python verifier (ground truth, no LLM)"
echo "==================================================================="
./venv/bin/python -m scripts.verify_manuscript --online --json data/outputs/verify_report.json || {
  echo ">> Python verifier FAILED — fix these before trusting any LLM critique." >&2
}

if [[ "${1:-}" == "--no-codex" ]]; then
  exit 0
fi
if ! command -v codex >/dev/null 2>&1; then
  echo ">> codex not on PATH; skipping cross-engine step." >&2
  exit 0
fi

echo
echo "==================================================================="
echo " STEP 2/2 — codex cross-engine check (read-only, JSON is ground truth)"
echo "==================================================================="

read -r -d '' PROMPT <<'EOF' || true
You are a SECOND, independent verification engine for a scientific manuscript. Your
job is to catch fabricated or mismatched specifics — NOT to make biology judgements.

Hard rules:
- The result JSON files in data/outputs/*.json and data/benchmark/*.json are GROUND
  TRUTH. The prose in docs/manuscript/preprint.md and docs/STUDY_SUMMARY.md must match
  them. Never assert a number from your own memory.
- A deterministic Python verifier already ran; its report is data/outputs/verify_report.json.
  Read it. Your value-add is ONLY discrepancies it might have missed.
- For every issue you raise, cite the exact file:line in the prose AND the exact JSON
  key+value that contradicts it. If you cannot cite both, do NOT raise it.
- Do NOT judge whether a variant is oncogenic (a human pathologist does that). ONLY
  check: (a) does every number in the prose match a JSON value? (b) is every variant
  named as one of OUR results actually present in cohort_interpretation.json or
  horak_results.json? (c) does the prose anywhere claim a statistically significant
  ACCURACY gain (it must NOT — Horak McNemar p=1.0 and p=0.61, non-significant)?
- Output: a short bulleted list of CONFIRMED discrepancies (file:line vs JSON key=value),
  or the single line "No discrepancies found beyond the Python verifier." Be terse.
  Do not rewrite files.
EOF

# read-only sandbox: codex may read the repo but cannot edit or run mutating cmds.
# (read-only sandbox does not prompt for approvals, so no approval flag is needed.)
codex exec \
  --sandbox read-only \
  --skip-git-repo-check \
  "$PROMPT"
