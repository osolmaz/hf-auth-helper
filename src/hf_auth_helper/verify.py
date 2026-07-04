"""Verify a pasted token against the Hub before anything stores it.

Network boundary of the tool: one authenticated ``whoami-v2`` call. The
verdict itself comes from :mod:`hf_auth_helper.scopes`.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from hf_auth_helper.scopes import TokenReport, evaluate_whoami

WHOAMI_URL = "https://huggingface.co/api/whoami-v2"
REQUEST_TIMEOUT_SECONDS = 30.0

Fetcher = Callable[[str], Mapping[str, object]]


class VerificationError(Exception):
    """The Hub could not confirm what the token is."""


def fetch_whoami(token: str) -> Mapping[str, object]:
    """Return the ``whoami-v2`` payload for ``token``."""
    request = urllib.request.Request(
        WHOAMI_URL,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise VerificationError("the Hub rejected the token (401)") from error
        raise VerificationError(f"whoami request failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise VerificationError(f"could not reach the Hub: {error}") from error
    if not isinstance(payload, Mapping):
        raise VerificationError("unexpected whoami response shape")
    return payload


def verify_token(token: str, fetch: Fetcher = fetch_whoami) -> TokenReport:
    """Fetch the token's identity and classify its scopes."""
    return evaluate_whoami(fetch(token))
