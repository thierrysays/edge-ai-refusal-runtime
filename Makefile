.PHONY: install test demo verify lint clean

install:
	pip install -e ".[dev]"

test:
	python -m pytest

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
