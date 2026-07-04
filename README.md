# hf-auth-helper

Set up safe, scoped Hugging Face authentication for agents.

Coding agents that read untrusted content (web pages, issues, datasets) can be
prompt-injected. If such an agent holds a normal `write` token, one injection
can delete your datasets, Spaces, and buckets. `hf-auth-helper` sets up
**propose-only** access instead: the agent can read and open pull requests,
but a human has to merge — nothing the agent does is irreversible.

What the agent **can** do with a token set up this way:

- Read the models, datasets, Spaces, and buckets in its scope (plus whatever
  optional reads you grant: collections, gated models, …).
- Propose changes to any git-based repo — models, datasets, Spaces — as pull
  requests with real commits, ready for your review.
- Open and comment on discussions, and manage its own pull requests.

What it **cannot** do, no matter how it is prompted:

- Merge pull requests (even its own), push to branches, or change any
  repository settings.
- Write to buckets at all: buckets have no pull-request mechanism and no
  version history, so any write would be unreviewable and unrecoverable —
  bucket write access is never part of any selection. Buckets stay
  read-only for the agent.
- Delete or overwrite anything, anywhere.

The trade-off to know about: the token can still *read* everything you scope
it to, so exfiltration of readable data remains your residual risk — see the
threat model in the spec.

## Usage

```sh
uvx hf-auth-helper agent login
```

Demo:

```text
$ uvx hf-auth-helper agent login
Installed 1 package in 9ms
Setting up a token your agent can't do damage with: it will be able
to read and open pull requests for your review. It cannot push
commits, merge, change settings, or delete anything.

? Use the recommended access settings for the agent? Yes
? Should the agent also have access to your organizations? No
The token will be able to: read repository contents, open pull requests and discussions, read gated models, read collections, see gated-repo access requests, read billing usage, read notifications. It cannot push commits, merge, change settings, or delete anything.

Create the token on this page — the right boxes are already ticked,
so you only need to name the token and click 'Create token':

  https://huggingface.co/settings/tokens/new?ownUserPermissions=repo.content.read&ownUserPermissions=repo.access.read&ownUserPermissions=collection.read&ownUserPermissions=discussion.write&ownUserPermissions=user.billing.read&ownUserPermissions=user.notifications.read&canReadGatedRepos=true&tokenType=fineGrained

? Open this page in a browser on this machine? No
? Paste the new token (shown as asterisks): *************************************
Verified: token 'osolmaz-hf-direct-access-bob' on account 'osolmaz' is propose-only —
the Hub confirms it cannot push commits, merge, change settings, or delete anything.
? How will the agent use this machine? a) This machine is the agent's — make the token its Hugging Face login
Done. This machine's Hugging Face login is now the agent token (saved as profile 'osolmaz-hf-direct-access-bob').
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
