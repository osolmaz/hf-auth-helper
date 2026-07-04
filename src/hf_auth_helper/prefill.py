"""Build Hugging Face token-creation URLs with scopes preselected.

The Hub's token form accepts the whole scope selection as query parameters,
so a correctly configured propose-only token is one link away. This module
composes that link.
"""

from urllib.parse import urlencode

TOKEN_FORM_URL = "https://huggingface.co/settings/tokens/new"

PROPOSE_ONLY_USER_PERMISSIONS = (
    "repo.content.read",
    "discussion.write",
)

PROPOSE_ONLY_ORG_PERMISSIONS = (
    "repo.content.read",
    "discussion.write",
)


def build_prefill_url(
    orgs: tuple[str, ...] = (),
    read_gated_repos: bool = False,
) -> str:
    """Return a token-form URL preselecting the propose-only scope set.

    ``orgs`` extends the same propose-only grants to each named organization.
    ``read_gated_repos`` additionally lets the token read public gated repos
    the account already has access to.
    """
    params: list[tuple[str, str]] = [("tokenType", "fineGrained")]
    params.extend(
        ("ownUserPermissions", permission) for permission in PROPOSE_ONLY_USER_PERMISSIONS
    )
    if read_gated_repos:
        params.append(("canReadGatedRepos", "true"))
    params.extend(("orgs", org) for org in orgs)
    if orgs:
        params.extend(("orgPermissions", permission) for permission in PROPOSE_ONLY_ORG_PERMISSIONS)
    return f"{TOKEN_FORM_URL}?{urlencode(params)}"
