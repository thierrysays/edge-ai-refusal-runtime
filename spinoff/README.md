# `spinoff/` — transit cargo, not part of this package

Two complete repositories are staged here, waiting to be pushed to their own
remotes. Neither is part of `edge-ai-refusal-runtime`: nothing here is imported
by `governed_edge_ai`, nothing here is packaged by `pyproject.toml`, and nothing
here is reached by `make qa` (which scopes `ruff`, `mypy`, `bandit` and `pytest`
to `src` and `tests`).

They are staged in this branch rather than pushed directly because the GitHub
App backing this session cannot create repositories — `POST /user/repos` returns
`403 Resource not accessible by integration`. The trees are finished; only the
remotes are missing.

| Directory | What it is | State |
|---|---|---|
| `measurement-harness/` | Instrument-agnostic power, latency and thermal measurement | 61 tests, ruff clean, `mypy --strict` clean, 96 % coverage |
| `fleet-ops-lab/` | A/B updates with automatic rollback, SBOM diffing, reproducible builds, waved rollouts | 67 tests, ruff clean, `mypy --strict` clean, 96 % coverage |

The rationale for their being separate repositories at all is
[ADR 0011](../docs/adr/0011-cross-cutting-work-lives-in-sibling-repositories.md).

## Transplanting them

Create the two empty repositories on GitHub — no README, no licence, no
`.gitignore`, since both trees carry their own — then, for each:

```bash
cd spinoff/measurement-harness
git init -b main
git add .
git commit -m "A measurement harness that refuses to call an estimate a measurement"
git remote add origin git@github.com:<owner>/measurement-harness.git
git push -u origin main
```

```bash
cd spinoff/fleet-ops-lab
git init -b main
git add .
git commit -m "Fleet operations for constrained nodes: silence is a rollback"
git remote add origin git@github.com:<owner>/fleet-ops-lab.git
git push -u origin main
```

Then delete this directory from `edge-ai-refusal-runtime` in a single commit.
Staging cargo in a repository that does not own it is fine for one branch and
becomes a maintenance problem on the second.
