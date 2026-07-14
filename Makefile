.PHONY: setup run dev start stop seed import

PIDFILE := /tmp/docex.pid
PORT    := 8000

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

run:
	docker compose up --build

start:
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "Already running (PID: $$(cat $(PIDFILE)))"; exit 1; fi
	PYTHONPATH=. nohup uvicorn app.main:app --port $(PORT) > /tmp/docex.log 2>&1 & echo $$! > $(PIDFILE)
	@sleep 1
	@if ! kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "Failed to start (check /tmp/docex.log)"; rm -f $(PIDFILE); exit 1; fi
	@echo "Started (PID: $$(cat $(PIDFILE)), port $(PORT))"

stop:
	@if [ -f $(PIDFILE) ] && kill $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "Stopped"; rm -f $(PIDFILE); \
	elif lsof -ti:$(PORT) > /dev/null 2>&1; then \
		kill $$(lsof -ti:$(PORT)) 2>/dev/null && echo "Stopped (stale)"; \
	else \
		echo "Not running"; \
	fi

dev:
	PYTHONPATH=. uvicorn app.main:app --reload --port $(PORT)

seed:
	python3 scripts/seed.py --output data/seed.jsonl

import:
	python3 scripts/bulk_import.py data/seed.jsonl
