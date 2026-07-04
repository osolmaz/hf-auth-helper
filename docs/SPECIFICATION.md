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
- **The token value is secret everywhere.** It is read with hidden input
  and is never echoed, logged, embedded in URLs or error messages, or
  written anywhere except the storage destination the user chose. This is
  a testable invariant: no output stream may ever contain the pasted
  token value.
- **Remote-first.** Assume the user is SSH'd into a remote box: the
  browser is never launched without asking first, and the printed URL is
  always the primary path.

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
- An explicit `--org` flag skips this step entirely (the answer was given
  on the command line); steps 1 and 3 still run.
- Platform constraint: the token form accepts a single `orgPermissions`
  block applied to *all* selected organizations — per-org scope
  customization is not possible and must not be attempted.

### Step 3 — Customize series (only if step 1 = No)

One yes/no question per optional capability, in this order. Each maps to
concrete scopes; each default is the recommended value (all Yes).

| # | Question | User scope | Org scope | Default |
|---|----------|-----------|-----------|---------|
| 1 | Read gated models it has access to (e.g. Llama)? | `canReadGatedRepos` | — | Yes |
| 2 | Read your collections? (helps it find your datasets and models) | `collection.read` | `collection.read` | Yes |
| 3 | See access requests for your gated repos? (includes requester names/emails) | `repo.access.read` | `repo.access.read` | Yes |
| 4 | Read your billing usage? (lets it check quota before heavy jobs) | `user.billing.read` | — | Yes |
| 5 | Read your notification inbox? (lets it notice replies to its pull requests) | `user.notifications.read` | — | Yes |
| 6 | Read org settings? (basic info about the orgs it works in) *(asked only if orgs selected)* | — | `org.read` | Yes |
| 7 | See the org's service accounts? (lists the org's automation accounts) *(asked only if orgs selected)* | — | `org.serviceAccounts.read` | Yes |

Each question carries a short parenthetical saying why the capability is
useful or what it exposes — every prompt must transmit why it matters.

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
> requests, read gated models. It cannot push commits, merge, change settings, or delete anything.

Then print the prefill URL (`https://huggingface.co/settings/tokens/new`
with `tokenType=fineGrained` and the selected scopes as query
parameters). The URL is always printed prominently — it is the primary
path, on the assumption that the user may be SSH'd into a remote box and
will open the link on another device.

The browser is never launched unprompted. After printing the URL, ask
(in the style of `gh auth login`):

> Open this page in a browser on this machine? (y/N)

The default is **No** when remote indicators are present
(`SSH_CONNECTION`/`SSH_TTY` set, or no display environment), **Yes**
otherwise. `--no-browser` skips the question and never opens one.
Whatever the answer, the flow continues to the hidden-input token
prompt.

### Step 5 — Verification

`GET /api/whoami-v2` with the pasted token. The response's
`auth.accessToken.fineGrained` block is the token's actual grant list,
per entity — no other API call is needed.

Safety check (gate):

- Role must be `fineGrained`.
- Every granted permission (global and scoped) must be in
  `SAFE_PERMISSIONS`.
- On refusal: name each violating permission and the role mismatch, store
  nothing, exit 1.
- On network/auth errors: report, store nothing, exit 2.

Scope mismatch report (informational, after the gate passes): compare the
granted set against what the flow configured, per entity, in both
directions:

- **Extras** (granted but not selected) — necessarily safe, or the gate
  would have refused. Reported as a note, e.g. "the token also has
  `user.billing.read`, which you didn't select."
- **Missing** (selected but not granted) — functional breakage, reported
  as a warning before storing, e.g. "no access to org `dutifuldev` — you
  selected it but the token doesn't include it", or "missing
  `discussion.write`: this token cannot open pull requests." The token is
  still stored (it is safe, just weaker than intended).

The mismatch comparison applies only to `fineGrained` tokens; classic
`read`/`write` tokens have no `fineGrained` block and never reach this
step because the role check refuses them first.

### Step 6 — Storage

The question is about usage, not files. If the machine has no active
`hf` login, there is nothing to displace and no decision to make: the
token becomes the machine's login automatically, with a line saying so.
Otherwise, one select:

> How will the agent use this machine?
> - This machine is the agent's — make the token its Hugging Face login
> - I also work here — give the token only to the agent, via an env file

The first choice makes the token the primary `hf` login (the user's
current login is preserved as a named profile per the Storage Model,
with a `hf auth switch` hint printed). The second writes an `HF_TOKEN=`
line into an env file (path asked, default `.env`) and states that the
user's own login is untouched.

A profile-only destination (register without activating) is not offered
in the wizard; it remains available via the `--profile NAME` flag. In
all destinations the registration name defaults to the token's display
name; for the automatic/primary path a name collision is resolved by
suffixing rather than prompting, since the name is bookkeeping there,
not a user choice. Written files are owner-only (mode 600). Semantics
follow the Storage Model below.

## Storage Model

The `hf` CLI's storage is a registry: `stored_tokens` holds named
credentials, and the `token` file is a pointer selecting the active one.
This tool maintains that model under one invariant:

> Every token value that passes through the tool has a name in the
> registry, and no credential value is ever destroyed — only superseded
> by name.

Rules:

- **Primary is not a separate destination.** Saving as primary means:
  register the token as a named profile in `stored_tokens`, then point
  the active-token file at it. There is no code path that writes the
  pointer without the registry entry.
- **Adoption before eviction.** Before repointing the active token, if
  the current token-file value is not registered under any name in
  `stored_tokens`, adopt it first: recover its display name via
  `whoami-v2`, falling back to `previous-<date>` if the lookup fails, and
  register it. Then repoint. Report the adoption to the user (e.g. "Your
  current token wasn't saved under a name — kept it as 'X'.").
- **Collision policy.** Saving a profile whose name exists with a
  *different* value: interactive with an explicit name → confirm
  replacement; interactive with a bookkeeping name (the primary path's
  automatic registration) → silently pick a suffixed free name;
  non-interactive → refuse with exit 2 (scripts must choose a new name
  deliberately). Same name with the *same* value is idempotent and
  silent. A confirmed
  replacement supersedes the *name*, never destroys the *value*: unless
  the old value is registered under another name, it is first re-registered
  under a suffixed name and the user is told. A collision refusal must
  happen before any other mutation (no adoption, no pointer move).
- **Env files are exports, not registry.** `--env` writes/replaces the
  `HF_TOKEN=` line in the given file and does not participate in the
  registry or the invariant; when an existing line was replaced, the
  message says so.

A testable property follows from the invariant: after any sequence of
tool operations, the set of token values stored on disk never shrinks
(except by an explicit future `agent logout`).

## Non-Interactive Behavior

When stdin or stdout is not a TTY, `agent login` runs without prompts and
the recommended selection is used; the browser is never opened. With no
destination flag, the token is stored as a named profile under its
display name; on a collision with a different value, refuse with exit 2.
Existing flags remain for scripting only — they select resources and
destinations, never scopes:

- `--org NAME` (repeatable), `--profile NAME` / `--primary` / `--env PATH`,
  `--url-only [--json]`, `--no-browser`.

`hf-auth-helper agent login --url-only` prints the recommended-selection
URL (with any `--org` values) and exits.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Token verified and stored (or URL printed) |
| 1 | Token refused: not propose-only |
| 2 | Error: empty paste, network failure, Hub rejection, non-interactive profile collision |
| 130 | Cancelled by user |

## Implementation Notes

- A single option table drives the customize questions, the URL builder,
  and the summary printer. Adding a future optional capability is one
  table row.
- The recommended selection is the table with every default applied — it
  is not a separately maintained list.
- The Storage Model section resolves the previously tracked multi-token
  gaps (silent profile overwrite, primary clobbering, unregistered
  primary); they are in scope for implementation.
