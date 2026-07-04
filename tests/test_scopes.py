"""Tests for the propose-only scope classifier."""

from hf_auth_helper.scopes import evaluate_whoami


def whoami_payload(role="fineGrained", scoped=None, global_permissions=None):
    return {
        "type": "user",
        "name": "someuser",
        "auth": {
            "type": "access_token",
            "accessToken": {
                "displayName": "test-token",
                "role": role,
                "fineGrained": {
                    "canReadGatedRepos": True,
                    "global": global_permissions or [],
                    "scoped": scoped or [],
                },
            },
        },
    }


def scope(kind, name, permissions):
    return {"entity": {"type": kind, "name": name}, "permissions": permissions}


def test_propose_only_token_passes():
    payload = whoami_payload(
        scoped=[
            scope("user", "someuser", ["repo.content.read", "discussion.write"]),
            scope("org", "someorg", ["repo.content.read", "discussion.write"]),
        ]
    )
    report = evaluate_whoami(payload)
    assert report.is_propose_only
    assert report.violations == ()


def test_full_agent_scope_selection_passes():
    payload = whoami_payload(
        scoped=[
            scope(
                "org",
                "someorg",
                [
                    "repo.content.read",
                    "repo.access.read",
                    "discussion.write",
                    "org.read",
                    "collection.read",
                    "org.serviceAccounts.read",
                ],
            ),
            scope(
                "user",
                "someuser",
                [
                    "repo.content.read",
                    "repo.access.read",
                    "collection.read",
                    "discussion.write",
                    "user.billing.read",
                    "user.notifications.read",
                ],
            ),
        ]
    )
    assert evaluate_whoami(payload).is_propose_only


def test_content_write_is_a_violation():
    payload = whoami_payload(
        scoped=[scope("user", "someuser", ["repo.content.read", "repo.content.write"])]
    )
    report = evaluate_whoami(payload)
    assert not report.is_propose_only
    assert [v.describe() for v in report.violations] == ["repo.content.write on user:someuser"]


def test_unknown_permission_fails_closed():
    payload = whoami_payload(scoped=[scope("user", "someuser", ["repo.future.superpower"])])
    report = evaluate_whoami(payload)
    assert not report.is_propose_only
    assert report.violations[0].permission == "repo.future.superpower"


def test_global_write_permission_is_a_violation():
    payload = whoami_payload(global_permissions=["inference.endpoints.write"])
    report = evaluate_whoami(payload)
    assert not report.is_propose_only
    assert report.violations[0].entity == "global"


def test_classic_write_token_is_rejected():
    payload = {
        "type": "user",
        "name": "someuser",
        "auth": {"type": "access_token", "accessToken": {"displayName": "w", "role": "write"}},
    }
    report = evaluate_whoami(payload)
    assert report.role == "write"
    assert not report.is_propose_only


def test_malformed_payload_is_rejected():
    report = evaluate_whoami({})
    assert report.role == ""
    assert not report.is_propose_only


def test_entity_without_name_is_reported_as_unknown():
    payload = whoami_payload(scoped=[{"entity": {}, "permissions": ["repo.content.write"]}])
    report = evaluate_whoami(payload)
    assert report.violations[0].entity == "unknown:unknown"
