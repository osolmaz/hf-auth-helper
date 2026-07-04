"""Tests for the verification boundary."""

import json
import urllib.error
from email.message import EmailMessage

import pytest

from hf_auth_helper.verify import VerificationError, fetch_whoami, verify_token


def test_verify_token_uses_fetcher():
    payload = {
        "name": "someuser",
        "auth": {
            "accessToken": {
                "displayName": "agent-token",
                "role": "fineGrained",
                "fineGrained": {
                    "scoped": [
                        {
                            "entity": {"type": "user", "name": "someuser"},
                            "permissions": ["repo.content.read", "discussion.write"],
                        }
                    ]
                },
            }
        },
    }
    report = verify_token("hf_x", fetch=lambda token: payload)
    assert report.is_propose_only
    assert report.username == "someuser"
    assert report.token_name == "agent-token"


def test_fetch_whoami_translates_401(monkeypatch):
    def raise_401(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", EmailMessage(), None)

    monkeypatch.setattr("urllib.request.urlopen", raise_401)
    with pytest.raises(VerificationError, match="401"):
        fetch_whoami("hf_bad")


def test_fetch_whoami_translates_other_http_errors(monkeypatch):
    def raise_500(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", EmailMessage(), None)

    monkeypatch.setattr("urllib.request.urlopen", raise_500)
    with pytest.raises(VerificationError, match="HTTP 500"):
        fetch_whoami("hf_x")


def test_fetch_whoami_translates_network_errors(monkeypatch):
    def raise_unreachable(request, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", raise_unreachable)
    with pytest.raises(VerificationError, match="could not reach"):
        fetch_whoami("hf_x")


def test_fetch_whoami_rejects_non_mapping_payload(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(["not", "a", "mapping"]).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())
    with pytest.raises(VerificationError, match="shape"):
        fetch_whoami("hf_x")


def test_fetch_whoami_sends_bearer_header(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"name": "someuser"}).encode()

    def fake_urlopen(request, timeout):
        captured["auth"] = request.get_header("Authorization")
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    payload = fetch_whoami("hf_x")
    assert payload == {"name": "someuser"}
    assert captured["auth"] == "Bearer hf_x"
    assert captured["url"] == "https://huggingface.co/api/whoami-v2"
