"""Command-line entry point for hf-auth-helper.

The default run is an interactive setup: pick the organizations the agent
should reach (detected from an existing ``hf`` login when possible), open
the Hub's token form with the propose-only scopes preselected, receive the
pasted token, verify against the Hub that it really is propose-only, and
store it where the user chooses. The token is refused — never stored — if
its scopes allow anything beyond reading and opening pull requests.
"""

import argparse
import json
import sys
import webbrowser
from getpass import getpass
from pathlib import Path
from typing import cast

from hf_auth_helper.prefill import build_prefill_url
from hf_auth_helper.scopes import TokenReport, extract_org_names
from hf_auth_helper.store import find_existing_token, save_env, save_primary, save_profile
from hf_auth_helper.vendored import load_questionary
from hf_auth_helper.verify import VerificationError, fetch_whoami, verify_token
from hf_auth_helper.wizard import (
    PromptBackend,
    SetupCancelled,
    ask_env_path,
    ask_profile_name,
    choose_destination,
    choose_orgs,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_ERROR = 2
EXIT_CANCELLED = 130


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.url_only:
        url = build_prefill_url(orgs=tuple(args.org), read_gated_repos=args.gated)
        print(json.dumps({"prefill_url": url}) if args.json else url)
        return EXIT_OK
    try:
        return _run_setup(args)
    except (SetupCancelled, KeyboardInterrupt):
        print("\nCancelled; nothing was stored.", file=sys.stderr)
        return EXIT_CANCELLED


def _run_setup(args: argparse.Namespace) -> int:
    prompts = _prompt_backend()
    orgs = tuple(args.org)
    if not orgs and prompts is not None:
        orgs = choose_orgs(prompts, _discover_orgs())
    _present_url(build_prefill_url(orgs=orgs, read_gated_repos=args.gated), not args.no_browser)
    return _receive_and_store(args, prompts)


def _receive_and_store(args: argparse.Namespace, prompts: PromptBackend | None) -> int:
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
    print(f"Verified: token '{report.token_name}' on account '{report.username}' is propose-only.")
    _store(args, prompts, token, report)
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


def _present_url(url: str, open_browser: bool) -> None:
    print("Create the token on this page (scopes are preselected):\n")
    print(f"  {url}\n")
    if open_browser and webbrowser.open(url):
        print("Opened it in your browser; keep the preselected scopes as they are.")


def _explain_refusal(report: TokenReport) -> None:
    print("Refused: this token is NOT propose-only. Nothing was stored.", file=sys.stderr)
    if report.role and report.role != "fineGrained":
        print(f"  - token role is '{report.role}', expected 'fineGrained'", file=sys.stderr)
    for violation in report.violations:
        print(f"  - unexpected permission: {violation.describe()}", file=sys.stderr)
    print("Delete it on https://huggingface.co/settings/tokens and retry.", file=sys.stderr)


def _store(
    args: argparse.Namespace,
    prompts: PromptBackend | None,
    token: str,
    report: TokenReport,
) -> None:
    destination = _resolve_destination(args, prompts)
    if destination == "primary":
        print(f"Saved as the primary hf token ({save_primary(token)}).")
    elif destination == "env":
        env_path = args.env or (ask_env_path(prompts) if prompts else ".env")
        print(f"Wrote HF_TOKEN to {save_env(token, Path(env_path))} (owner-only file mode).")
    else:
        _store_profile(args.profile, prompts, token, report)


def _resolve_destination(args: argparse.Namespace, prompts: PromptBackend | None) -> str:
    if args.primary:
        return "primary"
    if args.env is not None:
        return "env"
    if args.profile is not None or prompts is None:
        return "profile"
    return choose_destination(prompts)


def _store_profile(
    profile: str | None,
    prompts: PromptBackend | None,
    token: str,
    report: TokenReport,
) -> None:
    suggested = report.token_name or "propose-only"
    name = profile or (ask_profile_name(prompts, suggested) if prompts else suggested)
    path = save_profile(token, name)
    print(f"Saved as profile '{name}' ({path}).")
    print(f"Activate it with: hf auth switch --token-name {name}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hf-auth-helper",
        description="Set up safe, scoped Hugging Face authentication for agents.",
    )
    parser.add_argument(
        "--org",
        action="append",
        default=[],
        metavar="NAME",
        help="grant propose-only access to this organization (repeatable; skips the prompt)",
    )
    parser.add_argument(
        "--gated",
        action="store_true",
        help="include read access to public gated repos the account can access",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--profile",
        metavar="NAME",
        help="store as a named hf CLI profile (the default destination)",
    )
    destination.add_argument(
        "--primary",
        action="store_true",
        help="store as the primary hf CLI token",
    )
    destination.add_argument(
        "--env",
        metavar="PATH",
        help="write HF_TOKEN=... into this env file instead of the hf CLI",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="print the token-form URL without opening a browser",
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help="print the prefilled token-form URL and exit",
    )
    parser.add_argument("--json", action="store_true", help="with --url-only, print JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
