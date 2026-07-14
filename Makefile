.PHONY: setup run seed

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

run:
	docker compose up --build

seed:
	python3 scripts/seed.py --output data/seed.jsonl

import:
	python3 scripts/bulk_import.py data/seed.jsonl
