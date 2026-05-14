.PHONY: setup demo daemon init real ui ui-static lint clean help

PYTHON_VERSION := 3.12
PIPELINE := /Users/wbutler/Documents/Github/uk-smart-meter-data/src/transform_daily.py
WEB_HOST := 127.0.0.1
WEB_PORT := 8000
WEB_URL := http://$(WEB_HOST):$(WEB_PORT)
STATIC_UI_HOST := 127.0.0.1
STATIC_UI_PORT := 3000
STATIC_UI_URL := http://$(STATIC_UI_HOST):$(STATIC_UI_PORT)

help:
	@echo "Targets:"
	@echo "  make setup    Install uv (if missing), Python 3.12, deps, scaffold .env"
	@echo "  make demo     Run the agent end-to-end in DRY_RUN against the smart meter pipeline"
	@echo "  make daemon   Start the Mongo-watching daemon (for the frontend)"
	@echo "  make init     Create Mongo indexes"
	@echo "  make real     Run the agent without DRY_RUN (needs LLM + AWS configured)"
	@echo "  make ui       Start the read-only web UI with API-backed run history"
	@echo "  make ui-static Open a static UI-only preview without API-backed history"
	@echo "  make clean    Remove venv and caches"

setup:
	@command -v uv >/dev/null 2>&1 || { \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@export PATH="$$HOME/.local/bin:$$PATH" && uv python install $(PYTHON_VERSION) >/dev/null 2>&1 || true
	@export PATH="$$HOME/.local/bin:$$PATH" && uv sync
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example. Edit conn_string and re-run."; \
		cp .env.example .env; \
	fi
	@echo ""
	@echo "✓ Setup complete."
	@echo ""
	@echo "Minimum .env for a dry run:"
	@echo "  conn_string=<your atlas sandbox SRV uri>"
	@echo "  MONGO_DB_NAME=qa_agent"
	@echo "  DRY_RUN=1"
	@echo ""
	@echo "Then: make init && make demo"

init:
	@export PATH="$$HOME/.local/bin:$$PATH" && uv run python -m src.cli init

demo:
	@export PATH="$$HOME/.local/bin:$$PATH" && DRY_RUN=1 uv run python -m src.cli run \
		--pipeline "$(PIPELINE)" \
		--source-tables energy_smart_meter.raw_external_smart_meter \
		--destination-tables energy_smart_meter.silver_smart_meter_half_hourly_clean energy_smart_meter.gold_peak_demand_substation_day \
		--auto-answer "Daily rollup; should be complete by 9am next day."

real:
	@export PATH="$$HOME/.local/bin:$$PATH" && DRY_RUN=0 uv run python -m src.cli run \
		--pipeline "$(PIPELINE)" \
		--source-tables energy_smart_meter.silver_smart_meter_half_hourly_clean \
		--destination-tables energy_smart_meter.gold_peak_demand_substation_day \
		--auto-answer "Daily rollup; should be complete by 9am next day."

daemon:
	@export PATH="$$HOME/.local/bin:$$PATH" && uv run python -m src.daemon

ui:
	@command -v python3 >/dev/null 2>&1 || { \
		echo "python3 is required to launch the read-only UI."; \
		exit 1; \
	}
	@RUNNER=""; \
	if command -v uv >/dev/null 2>&1; then \
		RUNNER='uv run python'; \
	elif [ -x .venv/bin/python ]; then \
		RUNNER='.venv/bin/python'; \
	else \
		echo "No Python environment with project dependencies was found."; \
		echo "Run 'make setup' first, or use 'make ui-static' for a pure static preview."; \
		exit 1; \
	fi; \
	echo "Serving read-only UI at $(WEB_URL)"; \
	echo "Historical runs load from Mongo. New runs, answers, and stop actions are disabled."; \
	(sleep 1; python3 -m webbrowser "$(WEB_URL)" >/dev/null 2>&1 || true) & \
	if [ "$$RUNNER" = "uv run python" ]; then \
		export PATH="$$HOME/.local/bin:$$PATH" && QA_AGENT_WEB_READ_ONLY=1 uv run python -m src.webapp; \
	else \
		QA_AGENT_WEB_READ_ONLY=1 $$RUNNER -m src.webapp; \
	fi

ui-static:
	@command -v python3 >/dev/null 2>&1 || { \
		echo "python3 is required to serve the static UI preview."; \
		exit 1; \
	}
	@echo "Serving static UI preview at $(STATIC_UI_URL)"
	@echo "This does not start FastAPI, Mongo, AWS, or the QA agent."
	@echo "API-backed actions will show backend errors until src.webapp is running."
	@(sleep 1; python3 -m webbrowser "$(STATIC_UI_URL)" >/dev/null 2>&1 || true) & \
		cd chatbot-ui && python3 -m http.server $(STATIC_UI_PORT) --bind $(STATIC_UI_HOST)

clean:
	rm -rf .venv __pycache__ src/__pycache__ src/agent/__pycache__ src/agent/nodes/__pycache__ .pytest_cache .ruff_cache .mypy_cache
