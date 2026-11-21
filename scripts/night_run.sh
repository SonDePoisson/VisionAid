#!/usr/bin/env bash
# Exécution complète : tests rapides et lents, pipeline offline, temps réel 30 s (vidéo),
# faux téléphone 30 s (graphe téléphone → chemin), rejeu de chaque session réelle, agrégation.
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
  echo "--- run_offline (vidéo) ---"
  uv run python -m visionaid.apps.run_offline; OFF=$?
  echo "--- run_realtime (vidéo, 30 s) ---"
  uv run python -m visionaid.apps.run_realtime --duration 30; RT=$?
  echo "--- run_live (faux téléphone rejouant la vidéo, 30 s) ---"
  uv run python -m visionaid.apps.run_live --fake-phone data/video/appart.mp4 --duration 30 --rerun file; LIVE=$?
  echo "--- sessions réelles ---"
  SESS=0
  for d in data/sessions/*/; do
    [ -f "$d/frames.jsonl" ] || continue
    case "$d" in *calib*) continue ;; esac
    echo "    session $d"
    uv run python -m visionaid.apps.session_info "$d" || SESS=1
    uv run python -m visionaid.apps.run_offline --session "$d" || SESS=1
  done
  echo "--- agrégation ---"
  uv run python -c "import json; r=json.load(open('outputs/report.json')); r['night_run']={'fast':$FAST,'slow':$SLOW,'offline':$OFF,'realtime':$RT,'live_fake_phone':$LIVE,'sessions':$SESS}; json.dump(r, open('outputs/report.json','w'), indent=2, ensure_ascii=False); print(r['night_run'])"
  echo "=== fin $(date) : fast=$FAST slow=$SLOW offline=$OFF realtime=$RT live=$LIVE sessions=$SESS ==="
} 2>&1 | tee "$LOG"
