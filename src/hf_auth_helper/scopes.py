"""Classify Hugging Face access-token scopes from a ``whoami-v2`` payload.

The security core of hf-auth-helper: given the JSON the Hub returns for a
token, decide whether that token is *propose-only* — able to read and open
pull requests, but unable to write, merge, or delete anything.

The classification fails closed: any permission that is not explicitly known
to be safe is reported as a violation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

FINE_GRAINED_ROLE = "fineGrained"

# Permissions a propose-only token may hold. Everything else is a violation,
# including permissions this module has never seen before.
SAFE_PERMISSIONS = frozenset(
    {
        "repo.content.read",
        "repo.access.read",
        "collection.read",
        "discussion.write",
        "org.read",
        "org.serviceAccounts.read",
        "user.billing.read",
        "user.notifications.read",
    }
)


@dataclass(frozen=True)
class ScopeViolation:
    """A permission that breaks the propose-only guarantee."""

    entity: str
    permission: str

    def describe(self) -> str:
        return f"{self.permission} on {self.entity}"


@dataclass(frozen=True)
class TokenReport:
    """Verdict for one token, derived from its ``whoami-v2`` payload."""

    role: str
    violations: tuple[ScopeViolation, ...]
    username: str = ""
    token_name: str = ""
    granted: tuple[tuple[str, tuple[str, ...]], ...] = ()
    can_read_gated: bool = False

    @property
    def is_propose_only(self) -> bool:
        return self.role == FINE_GRAINED_ROLE and not self.violations


@dataclass(frozen=True)
class ScopeDiff:
    """Differences between what a run configured and what a token holds.

    Extras are informational (they passed the safety gate, so they are
    safe reads at most); missing entries mean the token is weaker than
    the run intended and some agent operations will fail.
    """

    extras: tuple[str, ...]
    missing_permissions: tuple[str, ...]
    missing_entities: tuple[str, ...]
    gated_extra: bool
    gated_missing: bool

    @property
    def clean(self) -> bool:
        return not (
            self.extras
            or self.missing_permissions
            or self.missing_entities
            or self.gated_extra
            or self.gated_missing
        )


def evaluate_whoami(payload: Mapping[str, object]) -> TokenReport:
    """Build a :class:`TokenReport` from a ``whoami-v2`` response payload."""
    access_token = _mapping(_mapping(payload.get("auth")).get("accessToken"))
    role = _text(access_token.get("role"))
    fine_grained = _mapping(access_token.get("fineGrained"))
    pairs = _iter_permissions(fine_grained)
    violations = [
        ScopeViolation(entity=entity, permission=permission)
        for entity, permission in pairs
        if permission not in SAFE_PERMISSIONS
    ]
    return TokenReport(
        role=role,
        violations=tuple(violations),
        username=_text(payload.get("name")),
        token_name=_text(access_token.get("displayName")),
        granted=_group_by_entity(pairs),
        can_read_gated=fine_grained.get("canReadGatedRepos") is True,
    )


def diff_scopes(
    report: TokenReport,
    expected: Mapping[str, tuple[str, ...]],
    expected_gated: bool,
) -> ScopeDiff:
    """Compare a token's granted scopes against a run's configuration.

    ``expected`` maps entity descriptions (``user:name``, ``org:name``) to
    the permissions the flow selected for them.
    """
    granted = dict(report.granted)
    extras = tuple(
        f"{permission} on {entity}"
        for entity, permissions in report.granted
        for permission in permissions
        if permission not in expected.get(entity, ())
    )
    missing_entities = tuple(entity for entity in expected if not granted.get(entity))
    missing_permissions = tuple(
        f"{permission} on {entity}"
        for entity, permissions in expected.items()
        if granted.get(entity)
        for permission in permissions
        if permission not in granted[entity]
    )
    return ScopeDiff(
        extras=extras,
        missing_permissions=missing_permissions,
        missing_entities=missing_entities,
        gated_extra=report.can_read_gated and not expected_gated,
        gated_missing=expected_gated and not report.can_read_gated,
    )


def _group_by_entity(pairs: list[tuple[str, str]]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped: dict[str, list[str]] = {}
    for entity, permission in pairs:
        grouped.setdefault(entity, []).append(permission)
    return tuple((entity, tuple(permissions)) for entity, permissions in grouped.items())


def extract_org_names(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Organization names the account belongs to, from a ``whoami-v2`` payload."""
    names = (_text(_mapping(org).get("name")) for org in _sequence(payload.get("orgs")))
    return tuple(name for name in names if name)


def _iter_permissions(fine_grained: Mapping[str, object]) -> list[tuple[str, str]]:
    pairs = [("global", permission) for permission in _texts(fine_grained.get("global"))]
    for scope in _sequence(fine_grained.get("scoped")):
        scope_mapping = _mapping(scope)
        entity = _describe_entity(_mapping(scope_mapping.get("entity")))
        pairs.extend(
            (entity, permission) for permission in _texts(scope_mapping.get("permissions"))
        )
    return pairs


def _describe_entity(entity: Mapping[str, object]) -> str:
    kind = _text(entity.get("type")) or "unknown"
    name = _text(entity.get("name")) or "unknown"
    return f"{kind}:{name}"


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    return ()


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _texts(value: object) -> list[str]:
    return [item for item in _sequence(value) if isinstance(item, str)]
