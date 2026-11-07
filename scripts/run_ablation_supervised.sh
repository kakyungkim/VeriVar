#!/bin/zsh
# Supervisor for scripts.run_context_ablation.
#
# The script writes its output only at the end, so any interruption loses the
# whole run. Two things interrupt it on a laptop: the machine sleeping (a closed
# lid on battery sleeps regardless of caffeinate) and the network moving. Both
# surface as openai.APIConnectionError once the request timeout added to
# src/classify/llm.py fires.
#
# So: wait for the API to be reachable, run, and if it dies without producing
# the output, wait and try again. One attempt takes about 17 minutes, so the run
# completes on the first stretch of uninterrupted wakefulness it gets.

cd "$(dirname "$0")/.." || exit 1   # repo root (script lives in scripts/)

OUT=data/outputs/context_ablation.json
LOG=data/outputs/context_ablation.log
MAX_ATTEMPTS=48

for attempt in $(seq 1 $MAX_ATTEMPTS); do
  if [ -f "$OUT" ]; then
    echo "=== 이미 결과 있음, 종료 $(date '+%H:%M:%S') ===" >> $LOG
    exit 0
  fi

  echo "=== 시도 $attempt/$MAX_ATTEMPTS  $(date '+%Y-%m-%d %H:%M:%S') ===" >> $LOG

  # API에 닿을 때까지 대기 (401도 도달한 것이므로 성공으로 본다)
  waited=0
  until curl -s -o /dev/null --max-time 10 https://api.openai.com/v1/models; do
    waited=$((waited + 60))
    echo "  네트워크 대기 ${waited}초  $(date '+%H:%M:%S')" >> $LOG
    sleep 60
  done

  caffeinate -ims ./venv/bin/python -u -m scripts.run_context_ablation >> $LOG 2>&1

  if [ -f "$OUT" ]; then
    echo "=== 성공 $(date '+%Y-%m-%d %H:%M:%S') ===" >> $LOG
    exit 0
  fi

  echo "=== 시도 $attempt 실패, 120초 뒤 재시도 ===" >> $LOG
  sleep 120
done

echo "=== $MAX_ATTEMPTS회 모두 실패, 포기 $(date '+%Y-%m-%d %H:%M:%S') ===" >> $LOG
exit 1
