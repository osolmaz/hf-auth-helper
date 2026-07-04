"""Tests for the option table, prefill URL builder, and summary."""

from urllib.parse import parse_qs, urlsplit

from hf_auth_helper.prefill import (
    OPTIONS,
    askable_options,
    build_prefill_url,
    org_permissions,
    reads_gated,
    recommended_selection,
    summarize,
    user_permissions,
)

# The field-tested reference URL recorded 2026-07-04 (docs/SPECIFICATION.md).
FIELD_TESTED_URL = (
    "https://huggingface.co/settings/tokens/new"
    "?ownUserPermissions=repo.content.read"
    "&ownUserPermissions=repo.access.read"
    "&ownUserPermissions=collection.read"
    "&ownUserPermissions=discussion.write"
    "&ownUserPermissions=user.billing.read"
    "&ownUserPermissions=user.notifications.read"
    "&canReadGatedRepos=true"
    "&tokenType=fineGrained"
    "&orgs=dutifuldev"
    "&orgPermissions=repo.content.read"
    "&orgPermissions=repo.access.read"
    "&orgPermissions=discussion.write"
    "&orgPermissions=org.read"
    "&orgPermissions=collection.read"
    "&orgPermissions=org.serviceAccounts.read"
)


def query(url):
    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.netloc == "huggingface.co"
    assert parts.path == "/settings/tokens/new"
    return parse_qs(parts.query)


def test_recommended_url_matches_field_tested_url_byte_for_byte():
    assert build_prefill_url(("dutifuldev",), recommended_selection()) == FIELD_TESTED_URL


def test_empty_selection_is_the_core_pair_only():
    params = query(build_prefill_url((), frozenset()))
    assert params["ownUserPermissions"] == ["repo.content.read", "discussion.write"]
    assert params["tokenType"] == ["fineGrained"]
    assert "canReadGatedRepos" not in params
    assert "orgs" not in params
    assert "orgPermissions" not in params


def test_single_option_selection_adds_only_its_scopes():
    params = query(build_prefill_url((), frozenset({"billing"})))
    assert params["ownUserPermissions"] == [
        "repo.content.read",
        "discussion.write",
        "user.billing.read",
    ]


def test_gated_option_controls_gated_param():
    assert reads_gated(frozenset({"gated"}))
    assert not reads_gated(frozenset({"billing"}))
    assert "canReadGatedRepos" in query(build_prefill_url((), frozenset({"gated"})))


def test_orgs_repeat_with_one_permission_block():
    params = query(build_prefill_url(("someorg", "otherorg"), frozenset()))
    assert params["orgs"] == ["someorg", "otherorg"]
    assert params["orgPermissions"] == ["repo.content.read", "discussion.write"]


def test_org_only_options_do_not_leak_into_user_permissions():
    selection = frozenset({"org_settings", "service_accounts"})
    assert user_permissions(selection) == ("repo.content.read", "discussion.write")
    assert "org.read" in org_permissions(selection)
    assert "org.serviceAccounts.read" in org_permissions(selection)


def test_askable_options_hides_org_only_questions_without_orgs():
    without_orgs = [option.key for option in askable_options(False)]
    with_orgs = [option.key for option in askable_options(True)]
    assert "org_settings" not in without_orgs
    assert "service_accounts" not in without_orgs
    assert with_orgs == [option.key for option in OPTIONS]


def test_every_option_maps_to_read_only_scopes():
    for option in OPTIONS:
        for permission in (*option.user_permissions, *option.org_permissions):
            assert permission.endswith(".read")


def test_summary_mentions_core_and_selected_capabilities():
    text = summarize((), frozenset({"gated"}))
    assert "read repository contents" in text
    assert "open pull requests" in text
    assert "read gated models" in text
    assert "read billing usage" not in text
    assert text.endswith("It cannot push commits, merge, change settings, or delete anything.")


def test_summary_skips_org_capabilities_without_orgs():
    text = summarize((), recommended_selection())
    assert "org settings" not in text
    with_orgs = summarize(("someorg",), recommended_selection())
    assert "read org settings" in with_orgs
    assert "someorg" in with_orgs
