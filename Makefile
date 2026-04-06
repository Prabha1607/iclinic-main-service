.PHONY: lint format typecheck validate

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src/

validate: lint typecheck
