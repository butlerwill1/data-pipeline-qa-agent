.PHONY: setup demo daemon init real lint clean help

PYTHON_VERSION := 3.12
PIPELINE := ../uk-smart-meter-data/energy-smart-meter-pipeline/src/transform_daily.py

help:
	@echo "Targets:"
	@echo "  make setup    Install uv (if missing), Python 3.12, deps, scaffold .env"
	@echo "  make demo     Run the agent end-to-end in DRY_RUN against the smart meter pipeline"
	@echo "  make daemon   Start the Mongo-watching daemon (for the frontend)"
	@echo "  make init     Create Mongo indexes"
	@echo "  make real     Run the agent without DRY_RUN (needs LLM + AWS configured)"
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
		--source-tables energy_smart_meter.raw_external_smart_meter \
		--destination-tables energy_smart_meter.silver_smart_meter_half_hourly_clean energy_smart_meter.gold_peak_demand_substation_day \
		--auto-answer "Daily rollup; should be complete by 9am next day."

daemon:
	@export PATH="$$HOME/.local/bin:$$PATH" && uv run python -m src.daemon

clean:
	rm -rf .venv __pycache__ src/__pycache__ src/agent/__pycache__ src/agent/nodes/__pycache__ .pytest_cache .ruff_cache .mypy_cache
