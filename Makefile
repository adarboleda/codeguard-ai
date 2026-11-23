.PHONY: all lint test

RUN_ID ?=

all:
	uv run codeguard all $(if $(RUN_ID),--run-id $(RUN_ID),)

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

test:
	uv run pytest
