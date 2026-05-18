.PHONY: bench bench-sota test lint typecheck

bench-sota:
	$(or $(PYTHON),python3) scripts/sota_bench.py

bench: bench-sota

test:
	pytest tests/

lint:
	ruff check src/ tests/

typecheck:
	mypy src/provably
