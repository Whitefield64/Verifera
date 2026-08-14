.DEFAULT_GOAL := help
.PHONY: help up ingest example status rebuild check

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

up:  ## Configure if needed, then start Postgres, the API and the UI
	@test -f .env || { cp .env.example .env; echo "Created .env from .env.example."; }
	@grep -qE '^OPENAI_API_KEY=.+' .env || { echo "OPENAI_API_KEY is empty in .env. Add it and run make up again."; exit 1; }
	@mkdir -p data/raw data/objects data/workspace data/eval-runs config
	docker compose up -d
	@echo
	@echo "UI on http://localhost:3000 · API on http://localhost:8000"
	@echo "Copy documents into data/raw/ and run 'make ingest' — or 'make example'"
	@echo "to load the demo corpus."

ingest:  ## Turn everything in data/raw/ into a corpus the assistant can answer from — costs money
	docker compose run --build --rm ingest python -m ingestion ingest

example:  ## Load the demo corpus: EU AI Act config, documents, ingestion — costs money
	@cp example/identity.md example/assistant.yaml example/routing.yaml config/
	@echo "Copied the EU AI Act configuration into config/."
	python3 example/fetch.py
	$(MAKE) ingest
	@docker compose restart api
	@echo
	@echo "Ready on http://localhost:3000"

status:  ## Document states and bbox coverage
	docker compose run --build --rm ingest python -m ingestion status

rebuild:  ## Repair the agent workspace from Postgres — no re-parse, no re-embed
	docker compose run --build --rm ingest python -m ingestion rebuild-workspace

check:  ## Everything CI runs
	ruff check engine
	cd engine/backend && python -m pytest tests -q
	cd engine/frontend && npx tsc --noEmit && npm test
	python3 engine/benchmark/run.py --validate-only
