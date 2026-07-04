# AGENTS.md

These instructions apply to this repository.

## Commands To Run Before Finishing

```sh
ruff format --check .
ruff check .
ty check src tests
pytest --cov=src/hf_auth_helper --cov-fail-under=85
python scripts/check-mutation.py --min-kill-rate 80
uvx slophammer-py@0.4.0 check .
```

CI runs the same gates; do not finish with any of them red.

## Rules

- Python 3.12+, standard library only in `src/` — this tool must stay
  runnable as a dependency-free single install. Dev tooling may use
  dependencies; shipped code may not.
- Type annotations on all public functions and meaningful helpers. No
  explicit `Any`; dynamic JSON is narrowed at the boundary
  (see `scopes.py` for the pattern).
- Security invariant: scope classification fails closed. Unknown permissions
  are violations. Never widen `SAFE_PERMISSIONS` without a test proving the
  permission cannot mutate or delete Hub content.
- Never print, log, or persist token values except where the user explicitly
  chose to store them.
- Keep domain logic (scope evaluation, URL building) free of IO. Network and
  filesystem access belong in the CLI layer only.
- Add or update tests for every behavior change.

## Slophammer

Quality gates are enforced with Slophammer standards:
https://raw.githubusercontent.com/dutifuldev/slophammer/refs/heads/main/docs/AGENT_ENTRYPOINT.md
