"""Tests for the propose-only scope classifier and the scope diff."""

from hf_auth_helper.scopes import diff_scopes, evaluate_whoami


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


def test_report_carries_granted_scopes_and_gated_flag():
    payload = whoami_payload(
        scoped=[
            scope("user", "someuser", ["repo.content.read", "discussion.write"]),
            scope("org", "someorg", ["repo.content.read"]),
        ],
        global_permissions=["collection.read"],
    )
    report = evaluate_whoami(payload)
    granted = dict(report.granted)
    assert granted["user:someuser"] == ("repo.content.read", "discussion.write")
    assert granted["org:someorg"] == ("repo.content.read",)
    assert granted["global"] == ("collection.read",)
    assert report.can_read_gated is True


def test_gated_flag_defaults_false_when_absent():
    payload = whoami_payload()
    del payload["auth"]["accessToken"]["fineGrained"]["canReadGatedRepos"]
    assert evaluate_whoami(payload).can_read_gated is False


def matching_report():
    return evaluate_whoami(
        whoami_payload(
            scoped=[
                scope("user", "someuser", ["repo.content.read", "discussion.write"]),
                scope("org", "someorg", ["repo.content.read", "discussion.write"]),
            ]
        )
    )


EXPECTED = {
    "user:someuser": ("repo.content.read", "discussion.write"),
    "org:someorg": ("repo.content.read", "discussion.write"),
}


def test_diff_is_clean_when_expected_matches_granted():
    diff = diff_scopes(matching_report(), EXPECTED, expected_gated=True)
    assert diff.clean


def test_diff_reports_extras():
    report = evaluate_whoami(
        whoami_payload(
            scoped=[
                scope(
                    "user",
                    "someuser",
                    ["repo.content.read", "discussion.write", "user.billing.read"],
                )
            ]
        )
    )
    diff = diff_scopes(
        report, {"user:someuser": ("repo.content.read", "discussion.write")}, expected_gated=True
    )
    assert diff.extras == ("user.billing.read on user:someuser",)
    assert not diff.clean


def test_diff_reports_missing_permission():
    report = evaluate_whoami(
        whoami_payload(scoped=[scope("user", "someuser", ["repo.content.read"])])
    )
    diff = diff_scopes(
        report, {"user:someuser": ("repo.content.read", "discussion.write")}, expected_gated=True
    )
    assert diff.missing_permissions == ("discussion.write on user:someuser",)
    assert diff.missing_entities == ()


def test_diff_reports_entirely_missing_entity():
    report = evaluate_whoami(
        whoami_payload(
            scoped=[scope("user", "someuser", ["repo.content.read", "discussion.write"])]
        )
    )
    diff = diff_scopes(
        report,
        {
            "user:someuser": ("repo.content.read", "discussion.write"),
            "org:someorg": ("repo.content.read", "discussion.write"),
        },
        expected_gated=True,
    )
    assert diff.missing_entities == ("org:someorg",)
    assert diff.missing_permissions == ()


def test_diff_reports_gated_both_directions():
    report = matching_report()
    assert diff_scopes(report, EXPECTED, expected_gated=False).gated_extra
    payload = whoami_payload(
        scoped=[
            scope("user", "someuser", ["repo.content.read", "discussion.write"]),
            scope("org", "someorg", ["repo.content.read", "discussion.write"]),
        ]
    )
    payload["auth"]["accessToken"]["fineGrained"]["canReadGatedRepos"] = False
    ungated = evaluate_whoami(payload)
    assert diff_scopes(ungated, EXPECTED, expected_gated=True).gated_missing
