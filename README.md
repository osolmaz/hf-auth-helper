# hf-auth-helper

Set up safe, scoped Hugging Face authentication for agents.

Coding agents that read untrusted content (web pages, issues, datasets) can be
prompt-injected. If such an agent holds a normal `write` token, one injection
can delete your datasets, Spaces, and buckets. `hf-auth-helper` sets up
**propose-only** access instead: the agent can read and open pull requests,
but a human has to merge — nothing the agent does is irreversible.

> Status: early. The prefill-URL command works; interactive verification and
> token storage are under development.

## Usage

Print a Hugging Face token-creation URL with the propose-only scopes
preselected — open it, name the token, click create:

```sh
uvx hf-auth-helper
uvx hf-auth-helper --org my-org --gated
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
ty check
pytest
```

## License

[MIT](LICENSE)
