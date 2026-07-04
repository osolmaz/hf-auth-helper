"""Tests for the CLI entry point."""

import json

import pytest

from hf_auth_helper.cli import main
from hf_auth_helper.scopes import ScopeViolation, TokenReport
from hf_auth_helper.verify import VerificationError

PROPOSE_ONLY = TokenReport(
    role="fineGrained", violations=(), username="someuser", token_name="agent-token"
)
WRITE_CAPABLE = TokenReport(
    role="fineGrained",
    violations=(ScopeViolation(entity="user:someuser", permission="repo.content.write"),),
    username="someuser",
    token_name="oops",
)


@pytest.fixture
def quiet_browser(monkeypatch):
    monkeypatch.setattr("hf_auth_helper.cli.webbrowser.open", lambda url: False)


def test_url_only_prints_prefill_url(capsys):
    assert main(["--url-only"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("https://huggingface.co/settings/tokens/new?")


def test_url_only_json_with_org_and_gated(capsys):
    assert main(["--url-only", "--org", "someorg", "--gated", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "orgs=someorg" in payload["prefill_url"]
    assert "canReadGatedRepos=true" in payload["prefill_url"]


def test_interactive_flow_saves_profile(monkeypatch, capsys, tmp_path, quiet_browser):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: PROPOSE_ONLY)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert main(["--no-browser"]) == 0
    out = capsys.readouterr().out
    assert "propose-only" in out
    assert "hf auth switch --token-name agent-token" in out
    assert "hf_secret" in (tmp_path / "stored_tokens").read_text()


def test_explicit_profile_name_skips_prompt(monkeypatch, capsys, tmp_path, quiet_browser):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: PROPOSE_ONLY)
    assert main(["--no-browser", "--profile", "bot"]) == 0
    assert "[bot]" in (tmp_path / "stored_tokens").read_text()


def test_primary_destination(monkeypatch, tmp_path, quiet_browser):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: PROPOSE_ONLY)
    assert main(["--no-browser", "--primary"]) == 0
    assert (tmp_path / "token").read_text() == "hf_secret\n"


def test_env_destination(monkeypatch, tmp_path, quiet_browser):
    env_file = tmp_path / ".env"
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: PROPOSE_ONLY)
    assert main(["--no-browser", "--env", str(env_file)]) == 0
    assert env_file.read_text() == "HF_TOKEN=hf_secret\n"


def test_write_capable_token_is_refused(monkeypatch, capsys, tmp_path, quiet_browser):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: WRITE_CAPABLE)
    assert main(["--no-browser"]) == 1
    err = capsys.readouterr().err
    assert "NOT propose-only" in err
    assert "repo.content.write on user:someuser" in err
    assert not (tmp_path / "stored_tokens").exists()


def test_wrong_role_is_named_in_refusal(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr(
        "hf_auth_helper.cli.verify_token",
        lambda token: TokenReport(role="write", violations=(), username="someuser"),
    )
    assert main(["--no-browser"]) == 1
    assert "token role is 'write'" in capsys.readouterr().err


def test_verification_error_reports_and_exits(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")

    def explode(token):
        raise VerificationError("the Hub rejected the token (401)")

    monkeypatch.setattr("hf_auth_helper.cli.verify_token", explode)
    assert main(["--no-browser"]) == 2
    assert "401" in capsys.readouterr().err


def test_empty_paste_exits_without_storing(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "  ")
    assert main(["--no-browser"]) == 2
    assert "nothing was stored" in capsys.readouterr().err


def test_browser_open_is_reported(monkeypatch, capsys):
    monkeypatch.setattr("hf_auth_helper.cli.webbrowser.open", lambda url: True)
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "")
    assert main([]) == 2
    assert "Opened it in your browser" in capsys.readouterr().out
