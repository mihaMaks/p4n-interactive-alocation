.PHONY: run test

run:
	. venv/bin/activate && python3 run_backend.py

test:
	. venv/bin/activate && python3 -m pytest tests/ -v
