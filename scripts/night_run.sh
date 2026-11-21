#!/usr/bin/env bash
# Exécution complète : tests rapides, tests lents, pipeline offline, temps réel 30 s, agrégation.
# Tout est journalisé dans outputs/night_run.log. Lancé sous caffeinate -i si disponible.
set -u
cd "$(dirname "$0")/.."
mkdir -p outputs
LOG=outputs/night_run.log
if [ -z "${VISIONAID_CAFFEINATED:-}" ] && command -v caffeinate >/dev/null 2>&1; then
  export VISIONAID_CAFFEINATED=1
  exec caffeinate -i bash "$0" "$@"
fi
{
  echo "=== VisionAId night run $(date) ==="
  echo "--- pytest -m 'not slow' ---"
  uv run pytest -m "not slow" -q; FAST=$?
  echo "--- pytest -m slow ---"
  uv run pytest -m slow -q --timeout=1800; SLOW=$?
  echo "--- run_offline ---"
  uv run python -m visionaid.apps.run_offline; OFF=$?
  echo "--- run_realtime (30 s) ---"
  uv run python -m visionaid.apps.run_realtime --duration 30; RT=$?
  echo "--- agrégation ---"
  uv run python -c "import json; r=json.load(open('outputs/report.json')); r['night_run']={'fast':$FAST,'slow':$SLOW,'offline':$OFF,'realtime':$RT}; json.dump(r, open('outputs/report.json','w'), indent=2, ensure_ascii=False); print(r['night_run'])"
  echo "=== fin $(date) : fast=$FAST slow=$SLOW offline=$OFF realtime=$RT ==="
} 2>&1 | tee "$LOG"
