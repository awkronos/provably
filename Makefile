.PHONY: bench bench-sota test lint typecheck

bench-sota:
	python scripts/sota_bench.py

bench: bench-sota

test:
	pytest tests/

lint:
	ruff check src/ tests/

typecheck:
	mypy src/provably
