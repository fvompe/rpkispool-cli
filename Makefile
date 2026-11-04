DATE ?= 20261103
CLI = uv run rpkispool-cli --date $(DATE)

.PHONY: hello test lint download verify summary

hello:
	@echo "This Makefile is intentionally left blank. Please check targets in it!"

test:
	uv run pytest tests

lint:
	uv run ruff check src
	uv run --with mypy mypy src

download:
	$(CLI) download --filelists

verify:
	$(CLI) verify

summary:
	$(CLI) summary vantage-points
