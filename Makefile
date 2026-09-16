UV := $(shell command -v uv 2>/dev/null || echo "$(CURDIR)/.tools/bin/uv")
export UV_CACHE_DIR := $(CURDIR)/.cache/uv
export PYTHONPATH := $(CURDIR)
PYTHON := $(CURDIR)/backend/.venv/bin/python

.PHONY: setup dev check smoke
setup:
	sh scripts/setup.sh "$(UV)"

dev:
	$(PYTHON) scripts/dev.py

check:
	$(PYTHON) -m unittest discover -s tests/integration -v
	$(PYTHON) -m unittest discover -s backend/tests/agents -v
	$(PYTHON) -m unittest discover -s backend/tests/auth -v
	npm --prefix frontend run build

smoke:
	$(PYTHON) scripts/smoke.py
