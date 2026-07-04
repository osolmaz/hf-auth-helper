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
