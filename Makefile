PY := uv run
.PHONY: setup test-fast test-all lint run-offline run-realtime night calibrate inspect

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
