.PHONY: install lint format-check typecheck test check

install:
	python -m pip install -e ".[dev,production]"

lint:
	ruff check .

format-check:
	ruff format --check .

typecheck:
	mypy .

test:
	PYTHONPATH=src pytest

check: lint format-check typecheck test
