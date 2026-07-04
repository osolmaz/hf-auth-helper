"""The option table: scope selection, prefill URL, and summary.

One table drives everything. Each :class:`Option` is an optional
capability with a plain-language question, the scopes it maps to, and a
summary phrase. The recommended selection is the table with every option
enabled — it is not a separately maintained list. The core pair
(``repo.content.read`` + ``discussion.write``) is never asked and always
included: it is the identity of the tool.

The Hub's token form accepts the whole scope selection as query
parameters; parameter order follows the field-tested URL recorded
2026-07-04 so the recommended selection reproduces it byte-for-byte.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

TOKEN_FORM_URL = "https://huggingface.co/settings/tokens/new"

CORE_USER_PERMISSIONS = ("repo.content.read", "discussion.write")
CORE_ORG_PERMISSIONS = ("repo.content.read", "discussion.write")

CORE_SUMMARY = ("read repository contents", "open pull requests and discussions")

# Permission order within each form parameter, matching the field-tested URL.
USER_PERMISSION_ORDER = (
    "repo.content.read",
    "repo.access.read",
    "collection.read",
    "discussion.write",
    "user.billing.read",
    "user.notifications.read",
)
ORG_PERMISSION_ORDER = (
    "repo.content.read",
    "repo.access.read",
    "discussion.write",
    "org.read",
    "collection.read",
    "org.serviceAccounts.read",
)


@dataclass(frozen=True)
class Option:
    """One optional capability: a question, its scopes, a summary phrase."""

    key: str
    question: str
    summary: str
    user_permissions: tuple[str, ...] = ()
    org_permissions: tuple[str, ...] = ()
    grants_gated_read: bool = False
    org_only: bool = False


OPTIONS = (
    Option(
        key="gated",
        question="Read gated models it has access to?",
        summary="read gated models",
        grants_gated_read=True,
    ),
    Option(
        key="collections",
        question="Read your collections? (helps it find your datasets and models)",
        summary="read collections",
        user_permissions=("collection.read",),
        org_permissions=("collection.read",),
    ),
    Option(
        key="access_requests",
        question="See access requests for your gated repos? (includes requester names/emails)",
        summary="see gated-repo access requests",
        user_permissions=("repo.access.read",),
        org_permissions=("repo.access.read",),
    ),
    Option(
        key="billing",
        question="Read your billing usage? (lets it check quota before heavy jobs)",
        summary="read billing usage",
        user_permissions=("user.billing.read",),
    ),
    Option(
        key="notifications",
        question="Read your notification inbox? (lets it notice replies to its pull requests)",
        summary="read notifications",
        user_permissions=("user.notifications.read",),
    ),
    Option(
        key="org_settings",
        question="Read org settings? (basic info about the orgs it works in)",
        summary="read org settings",
        org_permissions=("org.read",),
        org_only=True,
    ),
    Option(
        key="service_accounts",
        question="See the org's service accounts? (lists the org's automation accounts)",
        summary="see org service accounts",
        org_permissions=("org.serviceAccounts.read",),
        org_only=True,
    ),
)


def recommended_selection() -> frozenset[str]:
    """The blessed default: every option enabled."""
    return frozenset(option.key for option in OPTIONS)


def askable_options(orgs_selected: bool) -> tuple[Option, ...]:
    """The options the customize series asks, in table order."""
    return tuple(option for option in OPTIONS if orgs_selected or not option.org_only)


def user_permissions(selection: frozenset[str]) -> tuple[str, ...]:
    """User-namespace permissions for a selection, in form order."""
    return _ordered_permissions(selection, "user_permissions", USER_PERMISSION_ORDER)


def org_permissions(selection: frozenset[str]) -> tuple[str, ...]:
    """Org-namespace permissions for a selection, in form order."""
    return _ordered_permissions(selection, "org_permissions", ORG_PERMISSION_ORDER)


def reads_gated(selection: frozenset[str]) -> bool:
    """Whether the selection includes gated-repo read."""
    return any(option.grants_gated_read for option in OPTIONS if option.key in selection)


def build_prefill_url(orgs: tuple[str, ...], selection: frozenset[str]) -> str:
    """Return a token-form URL preselecting the selection's scopes."""
    params = [("ownUserPermissions", permission) for permission in user_permissions(selection)]
    if reads_gated(selection):
        params.append(("canReadGatedRepos", "true"))
    params.append(("tokenType", "fineGrained"))
    params.extend(("orgs", org) for org in orgs)
    if orgs:
        params.extend(("orgPermissions", permission) for permission in org_permissions(selection))
    return f"{TOKEN_FORM_URL}?{urlencode(params)}"


def summarize(orgs: tuple[str, ...], selection: frozenset[str]) -> str:
    """One human-readable sentence describing what the token can do."""
    phrases = list(CORE_SUMMARY)
    phrases.extend(
        option.summary
        for option in OPTIONS
        if option.key in selection and (orgs or not option.org_only)
    )
    where = f" across your account and {', '.join(orgs)}" if orgs else ""
    return (
        f"The token will be able to{where}: {', '.join(phrases)}. "
        "It cannot push commits, merge, change settings, or delete anything."
    )


def _ordered_permissions(
    selection: frozenset[str],
    field: str,
    order: tuple[str, ...],
) -> tuple[str, ...]:
    core = CORE_USER_PERMISSIONS if field == "user_permissions" else CORE_ORG_PERMISSIONS
    granted = set(core)
    for option in OPTIONS:
        if option.key in selection:
            granted.update(getattr(option, field))
    return tuple(permission for permission in order if permission in granted)
