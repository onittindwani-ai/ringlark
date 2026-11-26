PY=.venv/bin/python

.PHONY: e2e install test test-web constraints seed-check doctor check-env api worker web demo-note

install:
	@if command -v uv >/dev/null 2>&1; then \
	  uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -c constraints.txt -e packages/core-py -e "apps/api[dev]"; \
	elif PYBIN=$$(command -v python3.12 || command -v python3.13 || command -v python3.14); [ -n "$$PYBIN" ]; then \
	  $$PYBIN -m venv .venv && .venv/bin/pip install -c constraints.txt -e packages/core-py -e "apps/api[dev]"; \
	else \
	  echo "Neither uv nor Python 3.12 or newer found. Install uv (https://docs.astral.sh/uv/) or Python 3.12 or newer, then run make install again."; exit 1; \
	fi
	@command -v pnpm >/dev/null 2>&1 || { echo "pnpm not found. Run: corepack enable   (or: npm i -g pnpm)"; exit 1; }
	pnpm install

test:
	$(PY) -m pytest

test-web:
	pnpm --filter web test:unit

constraints:
	python3 tools/make_constraints.py .

seed-check:
	$(PY) tools/score_seed.py

doctor:
	$(PY) tools/doctor.py

check-env:
	python3 tools/check_env.py

api:
	$(PY) -m uvicorn ringlark.api.app:app_from_env --factory --port 8000 --proxy-headers

worker:
	$(PY) -m ringlark.worker

web:
	pnpm build && pnpm --filter web start

e2e:
	pnpm e2e
