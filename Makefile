.PHONY: bench bench-sota test lint typecheck

bench:
	python scripts/sota_bench.py

# Deprecated alias (old bare-Z3 comparison) — kept for reference, not default
bench-legacy:
	python scripts/optimal_bench.py

bench-sota:
	python scripts/sota_bench.py

test:
	pytest tests/

lint:
	ruff check src/ tests/

typecheck:
	mypy src/provably
