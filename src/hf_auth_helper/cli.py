"""Command-line entry point for hf-auth-helper.

The interactive flow (open the prefill URL, receive a pasted token, verify it
against the Hub, then store it) lands in later changes; this module currently
exposes the pieces that already work.
"""

import argparse
import json
import sys

from hf_auth_helper.prefill import build_prefill_url


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    url = build_prefill_url(orgs=tuple(args.org), read_gated_repos=args.gated)
    if args.json:
        print(json.dumps({"prefill_url": url}))
    else:
        print(url)
    return 0


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
        help="also grant propose-only access to this organization (repeatable)",
    )
    parser.add_argument(
        "--gated",
        action="store_true",
        help="include read access to public gated repos the account can access",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
