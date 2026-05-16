
COMPOSE ?= docker-compose

.PHONY: run logs test

run:
	$(COMPOSE) up -d --build

logs:
	$(COMPOSE) logs -f --tail=200

test:
	. venv/bin/activate && python3 -m pytest tests/ -v
