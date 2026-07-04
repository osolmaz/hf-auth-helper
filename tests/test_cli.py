"""Tests for the CLI entry point."""

import json

import pytest

from hf_auth_helper.cli import _discover_orgs, _remote_session, main
from hf_auth_helper.scopes import ScopeViolation, TokenReport
from hf_auth_helper.store import hf_home, read_profiles, save_profile
from hf_auth_helper.verify import VerificationError
from hf_auth_helper.wizard import ENV_FILE_CHOICE
from tests.test_wizard import FakeBackend

LOGIN = ["agent", "login", "--no-browser"]

PROPOSE_ONLY = TokenReport(
    role="fineGrained",
    violations=(),
    username="someuser",
    token_name="agent-token",
    granted=(
        (
            "user:someuser",
            (
                "repo.content.read",
                "repo.access.read",
                "collection.read",
                "discussion.write",
                "user.billing.read",
                "user.notifications.read",
            ),
        ),
    ),
    can_read_gated=True,
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


@pytest.fixture
def pasted_token(monkeypatch):
    # Non-interactive paste path; interactive tests feed the token through
    # the backend's password prompt instead.
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: PROPOSE_ONLY)


def test_bare_command_prints_help(capsys):
    assert main([]) == 0
    assert "agent" in capsys.readouterr().out


def test_bare_agent_prints_help(capsys):
    assert main(["agent"]) == 0
    assert "login" in capsys.readouterr().out


def test_url_only_prints_recommended_url(capsys):
    assert main(["agent", "login", "--url-only"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("https://huggingface.co/settings/tokens/new?")
    assert "user.billing.read" in out
    assert "canReadGatedRepos=true" in out


def test_url_only_json_with_org(capsys):
    assert main(["agent", "login", "--url-only", "--org", "someorg", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "orgs=someorg" in payload["prefill_url"]


def test_non_tty_flow_saves_profile_under_token_name(capsys, pasted_token, quiet_browser):
    assert main(LOGIN) == 0
    out = capsys.readouterr().out
    assert "The token will be able to" in out
    assert "hf auth switch --token-name agent-token" in out
    assert read_profiles() == {"agent-token": "hf_secret"}


def test_non_tty_profile_collision_refuses(capsys, pasted_token, quiet_browser):
    save_profile("hf_other", "agent-token")
    assert main(LOGIN) == 2
    assert "already exists" in capsys.readouterr().err
    assert read_profiles() == {"agent-token": "hf_other"}


def test_wizard_recommended_flow_auto_primary(monkeypatch, capsys, pasted_token, quiet_browser):
    backend = FakeBackend(
        confirms=[True, True],  # use recommended; org confirm
        checkboxes=[["someorg"]],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ("someorg",))
    assert main(LOGIN) == 0
    out = capsys.readouterr().out
    assert "orgs=someorg" in out
    assert "user.billing.read" in out
    # no existing login: the destination question is skipped, primary chosen
    assert "No Hugging Face credentials on this machine yet" in out
    assert backend.selects == []
    assert read_profiles() == {"agent-token": "hf_secret"}
    assert (hf_home() / "token").read_text() == "hf_secret\n"


def test_wizard_destination_asked_when_login_exists(
    monkeypatch, capsys, tmp_path, pasted_token, quiet_browser
):
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_existing_login\n")
    monkeypatch.setattr("hf_auth_helper.cli._display_name_of", lambda token: "my-login")
    backend = FakeBackend(
        confirms=[True, False],  # recommended; no orgs
        selects=[ENV_FILE_CHOICE],
        texts=["agent.env"],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main(LOGIN) == 0
    out = capsys.readouterr().out
    assert "Your own hf login on this machine is untouched." in out
    assert (hf_home() / "token").read_text() == "hf_existing_login\n"
    assert (tmp_path / "agent.env").read_text() == "HF_TOKEN=hf_secret\n"


def test_wizard_customize_flow_narrows_scopes(monkeypatch, capsys, pasted_token, quiet_browser):
    # decline recommended, decline orgs, then answer the 5 non-org questions:
    # gated yes, everything else no.
    backend = FakeBackend(
        confirms=[False, False, True, False, False, False, False],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main(LOGIN) == 0
    out = capsys.readouterr().out
    assert "canReadGatedRepos=true" in out
    assert "ownUserPermissions=user.billing.read" not in out
    assert "read gated models" in out
    assert "read billing usage" not in out


def test_org_flag_skips_org_prompt(monkeypatch, capsys, pasted_token, quiet_browser):
    backend = FakeBackend(
        confirms=[True],  # use recommended; no org confirm expected
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    assert main([*LOGIN, "--org", "flagorg"]) == 0
    assert "orgs=flagorg" in capsys.readouterr().out
    assert backend.checkboxes == []


def test_interactive_collision_confirm_replaces_and_preserves(
    monkeypatch, capsys, pasted_token, quiet_browser
):
    save_profile("hf_old", "agent-token")
    backend = FakeBackend(
        confirms=[True, False, True],  # recommended; no orgs; replace profile
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main([*LOGIN, "--profile", "agent-token"]) == 0
    assert "kept as 'agent-token-2'" in capsys.readouterr().out
    assert read_profiles() == {"agent-token": "hf_secret", "agent-token-2": "hf_old"}


def test_interactive_replace_skips_backup_when_value_registered_elsewhere(
    monkeypatch, capsys, pasted_token, quiet_browser
):
    save_profile("hf_old", "agent-token")
    save_profile("hf_old", "other-name")
    backend = FakeBackend(
        confirms=[True, False, True],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main([*LOGIN, "--profile", "agent-token"]) == 0
    assert read_profiles() == {"agent-token": "hf_secret", "other-name": "hf_old"}


def test_interactive_collision_decline_asks_new_name(
    monkeypatch, capsys, pasted_token, quiet_browser
):
    save_profile("hf_old", "agent-token")
    backend = FakeBackend(
        confirms=[True, False, False],  # recommended; no orgs; do NOT replace
        texts=["agent-token-2"],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main([*LOGIN, "--profile", "agent-token"]) == 0
    assert read_profiles() == {"agent-token": "hf_old", "agent-token-2": "hf_secret"}


def test_primary_adopts_unnamed_active_token(monkeypatch, capsys, pasted_token, quiet_browser):
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_old_login\n")
    monkeypatch.setattr("hf_auth_helper.cli._display_name_of", lambda token: "old-login")
    assert main([*LOGIN, "--primary"]) == 0
    out = capsys.readouterr().out
    assert "kept it as 'old-login'" in out
    profiles = read_profiles()
    assert profiles["old-login"] == "hf_old_login"
    assert profiles["agent-token"] == "hf_secret"
    assert (hf_home() / "token").read_text() == "hf_secret\n"


def test_primary_rotation_with_same_display_name(monkeypatch, capsys, pasted_token, quiet_browser):
    """Rotating a primary whose display name equals the new token's name.

    Regression: adoption used to claim the name the new token needed,
    refusing non-interactively or overwriting the just-adopted value.
    """
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_old_login\n")
    monkeypatch.setattr("hf_auth_helper.cli._display_name_of", lambda token: "agent-token")
    assert main([*LOGIN, "--primary"]) == 0
    out = capsys.readouterr().out
    assert "kept it as 'agent-token-2'" in out
    profiles = read_profiles()
    assert profiles == {"agent-token-2": "hf_old_login", "agent-token": "hf_secret"}
    assert (hf_home() / "token").read_text() == "hf_secret\n"


def test_primary_collision_refuses_before_any_mutation(
    monkeypatch, capsys, pasted_token, quiet_browser
):
    """Non-interactive --primary collision must not adopt or move anything."""
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_old_login\n")
    save_profile("hf_other", "agent-token")
    monkeypatch.setattr("hf_auth_helper.cli._display_name_of", lambda token: "old-login")
    assert main([*LOGIN, "--primary"]) == 2
    assert "already exists" in capsys.readouterr().err
    assert read_profiles() == {"agent-token": "hf_other"}
    assert (hf_home() / "token").read_text() == "hf_old_login\n"


def test_primary_does_not_adopt_registered_token(monkeypatch, capsys, pasted_token, quiet_browser):
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_old_login\n")
    save_profile("hf_old_login", "already-named")
    assert main([*LOGIN, "--primary"]) == 0
    assert "kept it as" not in capsys.readouterr().out
    assert read_profiles() == {"already-named": "hf_old_login", "agent-token": "hf_secret"}


def test_env_destination_reports_replacement(tmp_path, capsys, pasted_token, quiet_browser):
    env_file = tmp_path / ".env"
    env_file.write_text("HF_TOKEN=hf_old\n")
    assert main([*LOGIN, "--env", str(env_file)]) == 0
    assert "It replaces the HF_TOKEN that was in the file." in capsys.readouterr().out
    assert env_file.read_text() == "HF_TOKEN=hf_secret\n"


def test_mismatch_warns_on_missing_org(monkeypatch, capsys, pasted_token, quiet_browser):
    assert main([*LOGIN, "--org", "someorg"]) == 0
    out = capsys.readouterr().out
    assert "Warning: no access to org:someorg" in out


def test_mismatch_notes_extras(monkeypatch, capsys, quiet_browser):
    minimal_grant = TokenReport(
        role="fineGrained",
        violations=(),
        username="someuser",
        token_name="agent-token",
        granted=(("user:someuser", ("repo.content.read", "discussion.write", "org.read")),),
        can_read_gated=True,
    )
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: minimal_grant)
    assert main(LOGIN) == 0
    out = capsys.readouterr().out
    assert "Note: the token also has org.read on user:someuser" in out
    assert "Warning: missing user.billing.read on user:someuser" in out


def test_mismatch_flags_missing_pr_ability(monkeypatch, capsys, quiet_browser):
    no_pr = TokenReport(
        role="fineGrained",
        violations=(),
        username="someuser",
        token_name="agent-token",
        granted=(("user:someuser", ("repo.content.read",)),),
        can_read_gated=True,
    )
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: no_pr)
    assert main(LOGIN) == 0
    assert "cannot open pull requests" in capsys.readouterr().out


def test_write_capable_token_is_refused(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr("hf_auth_helper.cli.verify_token", lambda token: WRITE_CAPABLE)
    assert main(LOGIN) == 1
    err = capsys.readouterr().err
    assert "NOT propose-only" in err
    assert "repo.content.write on user:someuser" in err
    assert read_profiles() == {}


def test_wrong_role_is_named_in_refusal(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")
    monkeypatch.setattr(
        "hf_auth_helper.cli.verify_token",
        lambda token: TokenReport(role="write", violations=(), username="someuser"),
    )
    assert main(LOGIN) == 1
    assert "token role is 'write'" in capsys.readouterr().err


def test_verification_error_reports_and_exits(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "hf_secret")

    def explode(token):
        raise VerificationError("the Hub rejected the token (401)")

    monkeypatch.setattr("hf_auth_helper.cli.verify_token", explode)
    assert main(LOGIN) == 2
    assert "401" in capsys.readouterr().err


def test_empty_paste_exits_without_storing(monkeypatch, capsys, quiet_browser):
    monkeypatch.setattr("hf_auth_helper.cli.getpass", lambda prompt: "  ")
    assert main(LOGIN) == 2
    assert "nothing was stored" in capsys.readouterr().err


def test_ctrl_c_at_token_paste_is_graceful(monkeypatch, capsys, quiet_browser):
    def interrupt(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("hf_auth_helper.cli.getpass", interrupt)
    assert main(LOGIN) == 130
    assert "Cancelled; nothing was stored." in capsys.readouterr().err


def test_ctrl_c_in_wizard_cancels_whole_setup(monkeypatch, capsys, quiet_browser):
    backend = FakeBackend(confirms=[None])
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    assert main(LOGIN) == 130
    captured = capsys.readouterr()
    assert "Cancelled; nothing was stored." in captured.err
    assert "Create the token" not in captured.out


def test_browser_ask_defaults_no_on_ssh(monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 22 10.0.0.2 22")
    assert _remote_session() is True
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert _remote_session() is True
    monkeypatch.setenv("DISPLAY", ":0")
    assert _remote_session() is False


def test_browser_opens_only_after_confirmation(monkeypatch, capsys, pasted_token):
    opened = []
    monkeypatch.setattr(
        "hf_auth_helper.cli.webbrowser.open", lambda url: opened.append(url) or True
    )
    backend = FakeBackend(
        confirms=[True, False, True],  # recommended; no orgs; open browser
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main(["agent", "login"]) == 0
    assert len(opened) == 1
    assert "Opened it in your browser" in capsys.readouterr().out


def test_discover_orgs_uses_existing_token(monkeypatch):
    monkeypatch.setattr("hf_auth_helper.cli.find_existing_token", lambda: "hf_existing")
    monkeypatch.setattr(
        "hf_auth_helper.cli.fetch_whoami",
        lambda token: {"orgs": [{"name": "someorg"}, {"name": "otherorg"}]},
    )
    assert _discover_orgs() == ("someorg", "otherorg")


def test_discover_orgs_without_token_or_network(monkeypatch):
    monkeypatch.setattr("hf_auth_helper.cli.find_existing_token", lambda: None)
    assert _discover_orgs() == ()

    def explode(token):
        raise VerificationError("down")

    monkeypatch.setattr("hf_auth_helper.cli.find_existing_token", lambda: "hf_existing")
    monkeypatch.setattr("hf_auth_helper.cli.fetch_whoami", explode)
    assert _discover_orgs() == ()


def test_secrecy_no_output_stream_contains_the_token(
    monkeypatch, capsys, pasted_token, quiet_browser
):
    backend = FakeBackend(
        confirms=[True, False],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main(LOGIN) == 0
    captured = capsys.readouterr()
    assert "hf_secret" not in captured.out
    assert "hf_secret" not in captured.err


def test_destination_asked_when_profiles_exist_without_pointer(
    monkeypatch, capsys, pasted_token, quiet_browser
):
    """Stored profiles count as existing credentials even with no active login."""
    save_profile("hf_other_token", "earlier-agent")
    backend = FakeBackend(
        confirms=[True, False],
        selects=[ENV_FILE_CHOICE],
        texts=["agent.env"],
        passwords=["hf_secret"],
    )
    monkeypatch.setattr("hf_auth_helper.cli._prompt_backend", lambda: backend)
    monkeypatch.setattr("hf_auth_helper.cli._discover_orgs", lambda: ())
    assert main(LOGIN) == 0
    out = capsys.readouterr().out
    assert "No Hugging Face credentials" not in out
    assert backend.selects == []  # the select was consumed
