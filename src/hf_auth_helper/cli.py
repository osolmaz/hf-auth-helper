"""Command-line entry point for hf-auth-helper.

``hf-auth-helper agent login`` runs the interactive setup specified in
docs/SPECIFICATION.md: recommended-or-customize scope selection,
organization choice, the prefilled token form, verification against the
Hub, a scope-mismatch report, and registry-safe storage. The token is
refused — never stored — if its scopes allow anything beyond reading and
opening pull requests. Bare ``hf-auth-helper`` and ``hf-auth-helper
agent`` print help.
"""

import argparse
import datetime
import json
import os
import sys
import webbrowser
from getpass import getpass
from pathlib import Path
from typing import Protocol, cast

from hf_auth_helper.prefill import (
    askable_options,
    build_prefill_url,
    org_permissions,
    reads_gated,
    recommended_selection,
    summarize,
    user_permissions,
)
from hf_auth_helper.scopes import TokenReport, diff_scopes, evaluate_whoami, extract_org_names
from hf_auth_helper.store import (
    ProfileExistsError,
    find_existing_token,
    find_profile_name,
    read_active_token,
    read_profiles,
    save_env,
    save_primary,
    save_profile,
    unique_profile_name,
)
from hf_auth_helper.vendored import load_questionary
from hf_auth_helper.verify import VerificationError, fetch_whoami, verify_token
from hf_auth_helper.wizard import (
    PromptBackend,
    SetupCancelled,
    ask_env_path,
    ask_open_browser,
    ask_profile_name,
    ask_token,
    ask_use_recommended,
    choose_destination,
    choose_orgs,
    confirm_replace_profile,
    customize_selection,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_ERROR = 2
EXIT_CANCELLED = 130


class StoreRefusedError(Exception):
    """Storage was refused (e.g. a non-interactive profile collision)."""


def main(argv: list[str] | None = None) -> int:
    parser, agent_parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if getattr(args, "agent_command", None) != "login":
        (agent_parser if args.command == "agent" else parser).print_help()
        return EXIT_OK
    if args.url_only:
        url = build_prefill_url(tuple(args.org), recommended_selection())
        print(json.dumps({"prefill_url": url}) if args.json else url)
        return EXIT_OK
    try:
        return _run_login(args)
    except (SetupCancelled, KeyboardInterrupt):
        print("\nCancelled; nothing was stored.", file=sys.stderr)
        return EXIT_CANCELLED


def _run_login(args: argparse.Namespace) -> int:
    print(
        "Setting up a token your agent can't do damage with: it will be able\n"
        "to read and open pull requests for your review — never merge,\n"
        "overwrite, or delete.\n"
    )
    prompts = _prompt_backend()
    selection, orgs = _configure(args, prompts)
    print(summarize(orgs, selection))
    print()
    _present_url(build_prefill_url(orgs, selection), args, prompts)
    return _receive_and_store(args, prompts, selection, orgs)


def _configure(
    args: argparse.Namespace,
    prompts: PromptBackend | None,
) -> tuple[frozenset[str], tuple[str, ...]]:
    if prompts is None:
        return recommended_selection(), tuple(args.org)
    use_recommended = ask_use_recommended(prompts)
    orgs = tuple(args.org) or choose_orgs(prompts, _discover_orgs())
    if use_recommended:
        return recommended_selection(), orgs
    questions = [(option.key, option.question) for option in askable_options(bool(orgs))]
    return customize_selection(prompts, questions), orgs


def _receive_and_store(
    args: argparse.Namespace,
    prompts: PromptBackend | None,
    selection: frozenset[str],
    orgs: tuple[str, ...],
) -> int:
    if prompts is not None:
        token = ask_token(prompts)
    else:
        token = getpass("Paste the new token (input stays hidden): ").strip()
    if not token:
        print("No token pasted; nothing was stored.", file=sys.stderr)
        return EXIT_ERROR
    try:
        report = verify_token(token)
    except VerificationError as error:
        print(f"Verification failed: {error}. Nothing was stored.", file=sys.stderr)
        return EXIT_ERROR
    if not report.is_propose_only:
        _explain_refusal(report)
        return EXIT_REFUSED
    print(
        f"Verified: token '{report.token_name}' on account '{report.username}' is propose-only —\n"
        "the Hub confirms it can suggest changes but never merge, overwrite, or delete."
    )
    _report_mismatch(report, selection, orgs)
    try:
        _store(args, prompts, token, report)
    except StoreRefusedError as error:
        print(f"{error} Nothing was stored.", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def _prompt_backend() -> PromptBackend | None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    return cast("PromptBackend", load_questionary())


def _discover_orgs() -> tuple[str, ...]:
    existing = find_existing_token()
    if not existing:
        return ()
    try:
        return extract_org_names(fetch_whoami(existing))
    except VerificationError:
        return ()


def _remote_session() -> bool:
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _present_url(url: str, args: argparse.Namespace, prompts: PromptBackend | None) -> None:
    print("Create the token on this page — the right boxes are already ticked,")
    print("so you only need to name the token and click 'Create token':\n")
    print(f"  {url}\n")
    if args.no_browser or prompts is None:
        return
    if ask_open_browser(prompts, default=not _remote_session()) and webbrowser.open(url):
        print("Opened it in your browser; keep the preselected scopes as they are.")


def _explain_refusal(report: TokenReport) -> None:
    print("Refused: this token is NOT propose-only. Nothing was stored.", file=sys.stderr)
    if report.role and report.role != "fineGrained":
        print(f"  - token role is '{report.role}', expected 'fineGrained'", file=sys.stderr)
    for violation in report.violations:
        print(f"  - unexpected permission: {violation.describe()}", file=sys.stderr)
    print("Delete it on https://huggingface.co/settings/tokens and retry.", file=sys.stderr)


def _report_mismatch(
    report: TokenReport,
    selection: frozenset[str],
    orgs: tuple[str, ...],
) -> None:
    expected = {f"user:{report.username}": user_permissions(selection)}
    expected.update({f"org:{org}": org_permissions(selection) for org in orgs})
    diff = diff_scopes(report, expected, reads_gated(selection))
    if diff.clean:
        return
    for entity in diff.missing_entities:
        print(f"Warning: no access to {entity} — you selected it but the token doesn't include it.")
    for missing in diff.missing_permissions:
        note = " (this token cannot open pull requests)" if "discussion.write" in missing else ""
        print(f"Warning: missing {missing}{note}.")
    if diff.gated_missing:
        print("Warning: the token cannot read gated repos, which you selected.")
    for extra in diff.extras:
        print(f"Note: the token also has {extra}, which you didn't select.")
    if diff.gated_extra:
        print("Note: the token can also read gated repos, which you didn't select.")


def _store(
    args: argparse.Namespace,
    prompts: PromptBackend | None,
    token: str,
    report: TokenReport,
) -> None:
    destination = _resolve_destination(args, prompts)
    if destination == "primary":
        _store_primary(args, prompts, token, report)
    elif destination == "env":
        _store_env(args, prompts, token)
    else:
        _store_profile(args.profile, prompts, token, report)


def _resolve_destination(args: argparse.Namespace, prompts: PromptBackend | None) -> str:
    if args.primary:
        return "primary"
    if args.env is not None:
        return "env"
    if args.profile is not None or prompts is None:
        return "profile"
    if read_active_token() is None and not read_profiles():
        # A machine with no login and no stored tokens is an agent box;
        # there is nothing to displace, so there is no decision to ask.
        print("No Hugging Face credentials on this machine yet — making the agent token its login.")
        return "primary"
    return choose_destination(prompts)


def _store_profile(
    profile: str | None,
    prompts: PromptBackend | None,
    token: str,
    report: TokenReport,
) -> None:
    suggested = _suggested_name(report)
    initial = profile or (ask_profile_name(prompts, suggested) if prompts else suggested)
    name = _register(initial, prompts, token, save_profile)
    print(f"Saved as profile '{name}' — the agent is NOT logged in yet.")
    print(f"To activate it, run: hf auth switch --token-name {name}")


def _store_primary(
    args: argparse.Namespace,
    prompts: PromptBackend | None,
    token: str,
    report: TokenReport,
) -> None:
    def adopt_then_save_primary(token: str, name: str, *, replace: bool = False) -> Path:
        # Register first: a collision must abort before anything mutates.
        # Adoption then runs while the pointer still holds the old token,
        # and must know the final profile name so it never claims the name
        # the new token just took (same-name token rotation).
        save_profile(token, name, replace=replace)
        adopted = _adopt_active_token(token, avoid=name)
        if adopted:
            print(f"Your current token wasn't saved under a name — kept it as '{adopted}'.")
            print(f"Switch back to it anytime with: hf auth switch --token-name {adopted}")
        return save_primary(token, name, replace=True)

    name = _register(
        args.profile or _suggested_name(report),
        prompts,
        token,
        adopt_then_save_primary,
        auto_suffix=args.profile is None and prompts is not None,
    )
    print(
        f"Done. This machine's Hugging Face login is now the agent token "
        f"(saved as profile '{name}')."
    )


def _store_env(args: argparse.Namespace, prompts: PromptBackend | None, token: str) -> None:
    env_path = args.env or (ask_env_path(prompts) if prompts else ".env")
    path, replaced = save_env(token, Path(env_path))
    suffix = " It replaces the HF_TOKEN that was in the file." if replaced else ""
    print(f"Done. The agent can read HF_TOKEN from {path} (file readable only by you).{suffix}")
    print("Your own hf login on this machine is untouched.")


class _Saver(Protocol):
    def __call__(self, token: str, name: str, *, replace: bool = ...) -> Path: ...


def _suggested_name(report: TokenReport) -> str:
    return report.token_name or "propose-only"


def _register(
    name: str,
    prompts: PromptBackend | None,
    token: str,
    save: _Saver,
    *,
    auto_suffix: bool = False,
) -> str:
    while True:
        try:
            save(token, name)
            return name
        except ProfileExistsError:
            if auto_suffix:
                # The name is bookkeeping here, not a user choice; pick a
                # free one instead of interrupting (nothing is destroyed).
                name = unique_profile_name(name)
                continue
            if prompts is None:
                raise StoreRefusedError(
                    f"Profile '{name}' already exists with a different token."
                ) from None
            if _replace_confirmed(prompts, token, name, save):
                return name
            name = ask_profile_name(prompts, unique_profile_name(name))


def _replace_confirmed(prompts: PromptBackend, token: str, name: str, save: _Saver) -> bool:
    if not confirm_replace_profile(prompts, name):
        return False
    backup = _preserve_replaced_value(name)
    if backup:
        print(f"The previous token under '{name}' was kept as '{backup}'.")
    save(token, name, replace=True)
    return True


def _preserve_replaced_value(name: str) -> str | None:
    """Re-register a profile's current value before it is replaced.

    Keeps the storage invariant: replacement supersedes a *name*, never
    destroys a *value*. No-op when the value is also registered under
    another name.
    """
    profiles = read_profiles()
    old_value = profiles.get(name)
    if not old_value:
        return None
    if any(value == old_value for other, value in profiles.items() if other != name):
        return None
    backup = unique_profile_name(name)
    save_profile(old_value, backup)
    return backup


def _adopt_active_token(new_token: str, avoid: str) -> str | None:
    current = read_active_token()
    if not current or current == new_token or find_profile_name(current):
        return None
    base = _display_name_of(current) or _fallback_adopt_name()
    name = unique_profile_name(base, avoid=(avoid,))
    save_profile(current, name)
    return name


def _display_name_of(token: str) -> str:
    try:
        return evaluate_whoami(fetch_whoami(token)).token_name
    except VerificationError:
        return ""


def _fallback_adopt_name() -> str:
    return f"previous-{datetime.date.today().isoformat()}"


def _build_parser() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(
        prog="hf-auth-helper",
        description="Set up safe, scoped Hugging Face authentication for agents.",
    )
    subcommands = parser.add_subparsers(dest="command")
    agent = subcommands.add_parser("agent", help="tokens with agent scopes")
    agent_subcommands = agent.add_subparsers(dest="agent_command")
    login = agent_subcommands.add_parser(
        "login",
        help="create, verify, and store a propose-only agent token",
    )
    login.add_argument(
        "--org",
        action="append",
        default=[],
        metavar="NAME",
        help="grant agent access to this organization (repeatable; skips the org prompt)",
    )
    destination = login.add_mutually_exclusive_group()
    destination.add_argument(
        "--profile",
        metavar="NAME",
        help="store as a named hf CLI profile (the default destination)",
    )
    destination.add_argument(
        "--primary",
        action="store_true",
        help="store as the primary hf CLI token (registered as a profile too)",
    )
    destination.add_argument(
        "--env",
        metavar="PATH",
        help="write HF_TOKEN=... into this env file instead of the hf CLI",
    )
    login.add_argument(
        "--no-browser",
        action="store_true",
        help="never offer to open a browser",
    )
    login.add_argument(
        "--url-only",
        action="store_true",
        help="print the prefilled token-form URL and exit",
    )
    login.add_argument("--json", action="store_true", help="with --url-only, print JSON")
    return parser, agent


if __name__ == "__main__":
    raise SystemExit(main())
