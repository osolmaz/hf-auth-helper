# hf-auth-helper — Interactive Flow Specification

Status: agreed design, 2026-07-04. Supersedes the earlier preset-based
(`standard` / `minimal`) design; there are no named presets and no
scope-selection flags.

## Purpose

One interactive command that sets up **propose-only** Hugging Face access
for an agent: the agent can read and open pull requests, but can never
merge, push to protected content, modify buckets, change settings, or
delete anything. The tool composes the token-form prefill URL, verifies
the pasted token against the Hub, and stores it — refusing any token whose
scopes exceed propose-only.

## Command Structure

The flow in this document is triggered by:

```sh
uvx hf-auth-helper agent login
```

- `agent` is a command namespace: tokens with agent scopes. `login`
  creates, verifies, and stores one — mirroring `hf auth login`, but for
  an agent identity.
- Bare `hf-auth-helper` and bare `hf-auth-helper agent` print help listing
  the available (sub)commands; neither launches a flow.
- Scripting flags hang off the subcommand:
  `hf-auth-helper agent login --env .env`,
  `hf-auth-helper agent login --url-only`.
- Reserved for later (not in scope for this spec): `agent verify`
  (re-classify an existing token without storing), `agent logout` (remove
  a stored profile/env entry), `agent list` (show stored agent profiles).
  If the concept is ever upstreamed, the native shape is `hf agent login`.

## Rationale

Agents that read untrusted content (web pages, issues, datasets) can be
prompt-injected — the lethal trifecta: private data access + untrusted
input + the ability to communicate out. A default `write` token turns one
injection into deleted datasets, Spaces, and buckets. Client-side
guardrails cannot fix this: a compromised agent uses the raw credential,
not the wrapper around it. The only defense that holds is making the
credential itself incapable of destruction, enforced by the platform.

The Hub's permission model makes that expressible: opening a pull request
requires no write access (PRs are commits on `refs/pr/N`, pushed directly
to the target repo), while merging does. A token holding only reads plus
`discussion.write` can therefore propose anything and finalize nothing —
every change waits for a human merge. This was verified empirically
against the live Hub on 2026-07-04: with such a token, PR-with-commit
succeeds; merge, direct push to main, bucket file write, bucket delete,
and bucket creation all return 403.

## Threat Model

**Protected against by default — destruction and unreviewed change.** The
token cannot delete or overwrite anything: no merges, no pushes to
branches, no repo/bucket/settings mutation, no bucket writes (bucket
storage is non-versioned and unrecoverable, so bucket write access is
never granted in any configuration). Everything the agent produces is a
reviewable proposal. Residual nuisance capability: it can open, comment
on, rename, and close *its own* PRs — noisy at worst, reversible, and it
cannot touch anyone else's work.

**Not protected against — data exfiltration.** The token can *read*
everything in scope, including private repos and private buckets, and an
injected agent with internet access can send what it reads anywhere.
Nothing in this tool prevents that; scoping only shrinks the readable
surface. Users with sensitive private data should customize down the
optional reads, keep sensitive orgs out of the token's scope, or keep the
agent's world in a sandbox namespace. This limitation is stated here
deliberately: the tool's guarantee is "nothing irreversible," not
"nothing leaks."

## Principles

- **One recommended profile.** There is a single blessed scope selection
  (the field-tested selection recorded 2026-07-04, verified propose-only
  against the live Hub). Users either accept it or customize it — there is
  no second named profile.
- **Customization is a flow, not flags.** All configuration happens through
  plain-language prompts. No scope-selection command-line flags.
- **The core pair is never asked.** `repo.content.read` +
  `discussion.write` (read repo contents, open PRs/discussions) is the
  identity of the tool and is always included. Declining every optional
  question yields exactly this pair.
- **Presets are UX, verification is policy.** The verifier's
  `SAFE_PERMISSIONS` deny-list is the security boundary and is independent
  of what the flow selected. Any token whose scopes are all safe passes,
  even if broader than what this run configured; any unknown or
  write-capable scope is refused. Unknown scopes fail closed.
- **Cancel means cancel.** Ctrl-c at any prompt aborts the entire setup
  with one line on stderr and exit code 130. Nothing is stored.

## Interactive Flow

Prompts run only when stdin and stdout are TTYs. Backed by vendored
questionary through the `PromptBackend` protocol.

### Step 1 — Recommended or customize

> Use the recommended access settings for the agent? (Y/n)

- **Yes** (default): the recommended selection is used; skip step 3.
- **No**: the customize series in step 3 runs.

### Step 2 — Organizations

Unchanged from the current implementation:

- If an existing Hub credential is found (`HF_TOKEN`, then the `hf` CLI
  token file), the account's organizations are fetched from `whoami-v2`
  and offered as a checkbox list with an "Enter another organization
  manually…" escape hatch.
- With no credential (or no orgs), manual entry: one name per prompt,
  empty to finish, duplicates skipped.
- Declining the org question scopes the token to the personal namespace
  only.

### Step 3 — Customize series (only if step 1 = No)

One yes/no question per optional capability, in this order. Each maps to
concrete scopes; each default is the recommended value (all Yes).

| # | Question | User scope | Org scope | Default |
|---|----------|-----------|-----------|---------|
| 1 | Read gated models it has access to (e.g. Llama)? | `canReadGatedRepos` | — | Yes |
| 2 | Read your collections? | `collection.read` | `collection.read` | Yes |
| 3 | See access requests for your gated repos? | `repo.access.read` | `repo.access.read` | Yes |
| 4 | Read your billing usage? | `user.billing.read` | — | Yes |
| 5 | Read your notification inbox? | `user.notifications.read` | — | Yes |
| 6 | Read org settings? *(asked only if orgs selected)* | — | `org.read` | Yes |
| 7 | See the org's service accounts? *(asked only if orgs selected)* | — | `org.serviceAccounts.read` | Yes |

Org-scoped parts of an answer apply only when organizations were selected
in step 2.

### The recommended selection

Step 1 = Yes is equivalent to answering Yes to every question above:

- User: `repo.content.read`, `repo.access.read`, `collection.read`,
  `discussion.write`, `user.billing.read`, `user.notifications.read`,
  plus `canReadGatedRepos=true`.
- Org (per selected org): `repo.content.read`, `repo.access.read`,
  `discussion.write`, `org.read`, `collection.read`,
  `org.serviceAccounts.read`.

This matches the field-tested token-form URL byte-for-byte.

**Why each scope is in the default.** Every default except
`discussion.write` is read-only, so none of them widen the destruction
surface (which stays zero); what each one costs is readable — i.e.
exfiltratable — surface, which is why each is individually declinable in
the customize series.

| Scope | Why default-on | What it exposes if the agent is hijacked |
|-------|----------------|------------------------------------------|
| `repo.content.read` | Core: the agent must read repos to work on them | Contents of private repos in scope |
| `discussion.write` | Core: proposing changes is the point | PR/comment spam under your name (reversible) |
| `canReadGatedRepos` | Agent workloads commonly run gated models (e.g. Llama) | Gated model weights the account can access |
| `collection.read` | Cheap discovery aid for navigating your resources | Collection structure/metadata |
| `repo.access.read` | Lets the agent check gated-repo request state | Requester names/emails on your gated repos |
| `user.billing.read` | Lets the agent check usage/quota before heavy work | Billing/usage metadata |
| `user.notifications.read` | Lets the agent notice review feedback on its PRs | Activity metadata across private repos |
| `org.read` | Basic org visibility for org-scoped work | Org settings metadata |
| `org.serviceAccounts.read` | Part of the field-tested selection; org tooling visibility | Service-account inventory — reconnaissance value; the first candidate to decline in stricter setups |

The defaults reproduce the field-tested selection rather than the strict
minimum because the recommended path optimizes for the agent working
without friction; the customize series exists for users whose exfiltration
surface matters more than convenience.

### Step 4 — Summary and token form

Before opening the browser, print a short human-readable summary of what
the token will and will not be able to do, e.g.:

> The token will be able to: read your repos, read collections, open pull
> requests, read gated models. It cannot write, merge, or delete anything.

Then print the prefill URL (`https://huggingface.co/settings/tokens/new`
with `tokenType=fineGrained` and the selected scopes as query
parameters), open the browser unless `--no-browser`, and prompt for the
token with hidden input.

### Step 5 — Verification

`GET /api/whoami-v2` with the pasted token:

- Role must be `fineGrained`.
- Every granted permission (global and scoped) must be in
  `SAFE_PERMISSIONS`.
- On refusal: name each violating permission and the role mismatch, store
  nothing, exit 1.
- On network/auth errors: report, store nothing, exit 2.

### Step 6 — Storage

Unchanged: named `hf` CLI profile (default; suggests the token's display
name), primary `hf` CLI token, or `HF_TOKEN=` line in an env file. Written
files are owner-only (mode 600).

## Non-Interactive Behavior

When stdin or stdout is not a TTY, `agent login` runs without prompts and
the recommended selection is used. Existing flags remain for scripting
only — they select resources and destinations, never scopes:

- `--org NAME` (repeatable), `--profile NAME` / `--primary` / `--env PATH`,
  `--url-only [--json]`, `--no-browser`.

`hf-auth-helper agent login --url-only` prints the recommended-selection
URL (with any `--org` values) and exits.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Token verified and stored (or URL printed) |
| 1 | Token refused: not propose-only |
| 2 | Error: empty paste, network failure, Hub rejection |
| 130 | Cancelled by user |

## Implementation Notes

- A single option table drives the customize questions, the URL builder,
  and the summary printer. Adding a future optional capability is one
  table row.
- The recommended selection is the table with every default applied — it
  is not a separately maintained list.
- Known open issues tracked outside this spec: multi-token storage gaps
  (silent same-name profile overwrite; `--primary` clobbers the existing
  token file without preserving it and without registering the new token
  in `stored_tokens`).
