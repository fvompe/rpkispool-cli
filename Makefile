# optional, see .env.example
-include .env
export RPKISPOOL_DATE

CLI = uv run rpkispool-cli

.PHONY: hello test lint download verify coverage coverage-repos coverage-missing

hello:
	@echo "This Makefile is intentionally left blank. Please check targets in it!"

test:
	uv run pytest tests

lint:
	uv run ruff check src
	uv run --with mypy mypy src

download:
	$(CLI) download

verify:
	$(CLI) verify

coverage:
	$(CLI) coverage vantage-points

coverage-repos:
	$(CLI) coverage repositories

coverage-missing:
	$(CLI) coverage missing
