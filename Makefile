.PHONY: bench bench-sota test coverage lint typecheck

bench-sota:
	$(or $(PYTHON),python3) scripts/sota_bench.py

bench: bench-sota

test:
	$(or $(PYTHON),.venv/bin/python) -m pytest tests/

# Measured gate for the ">=95%" claim pinned in tests/test_coverage_95.py.
# Same recipe and threshold as CI (coverage report --fail-under=95): coverage
# is asserted by the runner that measures it — no skip-if-no-artifact test.
coverage:
	$(or $(PYTHON),.venv/bin/python) -m coverage erase
	$(or $(PYTHON),.venv/bin/python) -m coverage run --source=provably -m pytest tests/
	$(or $(PYTHON),.venv/bin/python) -m coverage report --fail-under=95

lint:
	ruff check src/ tests/

typecheck:
	$(or $(PYTHON),.venv/bin/python) -m mypy src/provably
