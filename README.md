# hf-auth-helper

Set up safe, scoped Hugging Face authentication for agents.

Coding agents that read untrusted content (web pages, issues, datasets) can be
prompt-injected. If such an agent holds a normal `write` token, one injection
can delete your datasets, Spaces, and buckets. `hf-auth-helper` sets up
**propose-only** access instead: the agent can read and open pull requests,
but a human has to merge — nothing the agent does is irreversible.

## Usage

```sh
uvx hf-auth-helper agent login
```

One interactive command:

1. **Recommended or customize** — accept the field-tested access settings,
   or answer plain-language yes/no questions ("Read gated models?", "Read
   your billing usage?", …) to narrow them. Reading repo contents and
   opening pull requests are always included; write access never is.
2. **Organizations** — if you're already logged into the `hf` CLI, your orgs
   are detected and offered as a checklist; otherwise enter names manually.
3. **Token form** — a summary of what the token will be able to do, then the
   Hugging Face token page URL with your scopes preselected. Open it on any
   device (the tool assumes you may be SSH'd into a remote box and only
   opens a local browser if you say yes); name the token and click create.
4. **Verification** — paste the token (input stays hidden) and it is checked
   against the Hub: if its scopes allow anything beyond reading and opening
   pull requests, it is **refused** with the violating permissions named,
   and nothing is stored. Differences from what you configured are reported.
5. **Storage** — keep it as a named `hf` CLI profile (activate with
   `hf auth switch`), make it the primary token (your current login is
   preserved as a named profile, never destroyed), or write an `HF_TOKEN=`
   line into an env file for a single agent process.

Scripting (no prompts when not a TTY; flags select resources and
destinations, never scopes):

```sh
uvx hf-auth-helper agent login --org my-org --profile my-agent
uvx hf-auth-helper agent login --env /path/to/agent/.env
uvx hf-auth-helper agent login --url-only        # just print the prefill URL
```

Whatever you select, write capability is limited to opening PRs and
discussions. A token created this way cannot push to main, merge PRs, modify
buckets, change settings, or delete anything. What it can still do is *read*
everything you granted it — see the threat model in
[docs/SPECIFICATION.md](docs/SPECIFICATION.md) for why "nothing irreversible"
is the guarantee, not "nothing leaks".

The full behavior contract, threat model, and design rationale live in
[docs/SPECIFICATION.md](docs/SPECIFICATION.md).

## License

[MIT](LICENSE)
