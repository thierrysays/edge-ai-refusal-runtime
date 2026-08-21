.PHONY: install test smoke unit functional security docs pentest fuzz demo verify tamper lint typecheck sast audit cover qa clean

install:
	pip install -e ".[dev]"

# ---------------------------------------------------------------- test layers
# Seven layers, each answering a different question, each runnable alone. Run in
# this order: the fast shallow ones first, so a broken build fails in a second
# rather than in twenty, and so a failure names its own category before anyone
# reads the output.

smoke:      ## does it start, and does every entry point answer at all
	python -m pytest tests/test_smoke.py -q

unit:       ## does each control refuse exactly what it is supposed to refuse
	python -m pytest tests/test_journal.py tests/test_policy.py \
		tests/test_registry_admission.py tests/test_oversight_and_marking.py -q

functional: ## do the journeys leave the cell in the state the operator expected
	python -m pytest tests/test_runtime_e2e.py tests/test_cli.py -q

security:   ## attacks on the controls, rather than exercises of them
	python -m pytest tests/test_adversarial.py -q

docs:       ## the control map is a contract, and links have to resolve
	python -m pytest tests/test_repository.py -q

test: smoke unit functional security docs

# ------------------------------------------------------------------- pen-test
# The fuzzer asserts one property: verify_journal() and validate_card() answer
# with a result or a named governance error, for any input at all. It found one
# defect on its first run, recorded in docs/BUILD_LOG.en.md.

fuzz:
	python tools/fuzz_evidence.py --iterations 4000 --seed 12
	python tools/fuzz_evidence.py --iterations 4000 --seed 2026

pentest: security fuzz sast

demo:
	python -m governed_edge_ai.cli demo --out ./run --parts 16

verify:
	python -m governed_edge_ai.cli verify \
		--journal ./run/journal.jsonl \
		--trust-store ./run/trust-store.json

# Proof that the controls are load-bearing: tamper with the evidence and watch
# verification name the sequence number where it broke.
tamper: demo
	@python -c "import json,sys; \
p='./run/journal.jsonl'; \
L=[json.loads(l) for l in open(p) if l.strip()]; \
[r['body'].__setitem__('effect','allow') for r in L if r['kind']=='policy_decision' and r['body'].get('effect')=='deny'][:1]; \
open(p,'w').writelines(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in L)"
	@python -m governed_edge_ai.cli verify --journal ./run/journal.jsonl || true

clean:
	rm -rf run build dist .pytest_cache **/__pycache__ *.egg-info

# --------------------------------------------------------------- quality gate
# `make qa` is what CI runs. Everything in it fails the build; nothing in it
# prints a warning and continues, because a warning nobody must act on is a
# warning nobody reads.

lint:
	python -m ruff check src tests tools

typecheck:
	python -m mypy

sast:
	python -m bandit -q -r src tools

audit:
	python -m pip_audit --progress-spinner off

cover:
	python -m pytest --cov --cov-report=term-missing

qa: lint typecheck sast audit cover
