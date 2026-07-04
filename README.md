# hf-auth-helper

Set up safe, scoped Hugging Face authentication for agents.

Coding agents that read untrusted content (web pages, issues, datasets) can be
prompt-injected. If such an agent holds a normal `write` token, one injection
can delete your datasets, Spaces, and buckets. `hf-auth-helper` sets up
**propose-only** access instead: the agent can read and open pull requests,
but a human has to merge — nothing the agent does is irreversible.

## Usage

```sh
uvx hf-auth-helper
```

One interactive command:

1. **Organizations** — if you're already logged into the `hf` CLI, your orgs
   are detected and offered as a checklist; otherwise (or additionally) enter
   names manually.
2. **Token form** — your browser opens the Hugging Face token page with the
   propose-only scopes preselected; you just name the token and click create.
3. **Verification** — paste the token (input stays hidden) and it is checked
   against the Hub: if its scopes allow anything beyond reading and opening
   pull requests, it is **refused** with the violating permissions named, and
   nothing is stored.
4. **Storage** — keep it as a named `hf` CLI profile (activate with
   `hf auth switch`), make it the primary token, or write an `HF_TOKEN=` line
   into an env file for a single agent process.

Non-interactive use:

```sh
uvx hf-auth-helper --org my-org --gated --profile my-agent
uvx hf-auth-helper --env /path/to/agent/.env
uvx hf-auth-helper --url-only --org my-org        # just print the prefill URL
```

The selected scopes are `repo.content.read` (read repo contents) and
`discussion.write` (open PRs and discussions) — nothing else. A token created
this way cannot push to main, merge PRs, modify buckets, change settings, or
delete anything.

## Development

```sh
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
ty check src tests
pytest --cov=src/hf_auth_helper --cov-fail-under=85
python scripts/check-mutation.py --min-kill-rate 80
uvx slophammer-py@0.4.0 check .
```

The interactive prompts use [questionary](https://github.com/tmbo/questionary),
vendored under `src/hf_auth_helper/vendor` (refresh with
`python scripts/vendor.py`) so the published package has zero dependencies.

## License

[MIT](LICENSE)
