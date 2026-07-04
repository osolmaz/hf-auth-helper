"""Tests for the token-form prefill URL builder."""

from urllib.parse import parse_qs, urlsplit

from hf_auth_helper.prefill import build_prefill_url


def query(url):
    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.netloc == "huggingface.co"
    assert parts.path == "/settings/tokens/new"
    return parse_qs(parts.query)


def test_minimal_url_is_propose_only():
    params = query(build_prefill_url())
    assert params["tokenType"] == ["fineGrained"]
    assert params["ownUserPermissions"] == ["repo.content.read", "discussion.write"]
    assert "orgs" not in params
    assert "canReadGatedRepos" not in params


def test_orgs_add_org_permission_block():
    params = query(build_prefill_url(orgs=("someorg", "otherorg")))
    assert params["orgs"] == ["someorg", "otherorg"]
    assert params["orgPermissions"] == ["repo.content.read", "discussion.write"]


def test_gated_flag_adds_gated_read():
    params = query(build_prefill_url(read_gated_repos=True))
    assert params["canReadGatedRepos"] == ["true"]
