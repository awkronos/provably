.PHONY: bench test lint typecheck

bench:
	python scripts/optimal_bench.py

test:
	pytest tests/

lint:
	ruff check src/ tests/

typecheck:
	mypy src/provably
