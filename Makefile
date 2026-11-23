PY := uv run
.PHONY: app setup test-fast test-all lint run-offline run-realtime night calibrate inspect run-phone fake-phone run-live run-live-fake

setup:
	uv sync

lint:
	$(PY) ruff check src tests && $(PY) ruff format --check src tests

test-fast:
	$(PY) pytest -m "not slow" -q

test-all:
	$(PY) pytest -q --timeout=1800

inspect:
	$(PY) python -m visionaid.apps.inspect_data

calibrate:
	$(PY) python -m visionaid.apps.calibrate_reid

run-offline:
	$(PY) python -m visionaid.apps.run_offline

run-realtime:
	$(PY) python -m visionaid.apps.run_realtime

night:
	bash scripts/night_run.sh

run-phone:
	$(PY) python -m visionaid.apps.run_phone

fake-phone:
	$(PY) python -m visionaid.phone.fake_phone --duration 30

run-live:
	$(PY) python -m visionaid.apps.run_live --rerun live

run-live-fake:
	$(PY) python -m visionaid.apps.run_live --fake-phone data/video/appart.mp4 --duration 60 --rerun live

app:
	$(PY) visionaid
