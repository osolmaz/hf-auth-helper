"""Tests for token storage destinations."""

import stat

from hf_auth_helper.store import find_existing_token, hf_home, save_env, save_primary, save_profile


def mode_of(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_hf_home_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "custom"))
    assert hf_home() == tmp_path / "custom"


def test_hf_home_defaults_to_cache(monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    assert str(hf_home()).endswith(".cache/huggingface")


def test_find_existing_token_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_TOKEN", "hf_from_env")
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert find_existing_token() == "hf_from_env"


def test_find_existing_token_reads_token_file(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    (tmp_path / "token").write_text("hf_from_file\n")
    assert find_existing_token() == "hf_from_file"


def test_find_existing_token_handles_absence(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert find_existing_token() is None
    (tmp_path / "token").write_text("  \n")
    assert find_existing_token() is None


def test_save_profile_creates_ini(tmp_path):
    path = tmp_path / "stored_tokens"
    result = save_profile("hf_secret", "agent", stored_tokens_path=path)
    assert result == path
    content = path.read_text()
    assert "[agent]" in content
    assert "hf_token = hf_secret" in content
    assert mode_of(path) == 0o600


def test_save_profile_preserves_other_profiles(tmp_path):
    path = tmp_path / "stored_tokens"
    path.write_text("[existing]\nhf_token = hf_old\n")
    save_profile("hf_new", "agent", stored_tokens_path=path)
    content = path.read_text()
    assert "hf_old" in content
    assert "hf_new" in content


def test_save_profile_updates_existing_profile(tmp_path):
    path = tmp_path / "stored_tokens"
    save_profile("hf_first", "agent", stored_tokens_path=path)
    save_profile("hf_second", "agent", stored_tokens_path=path)
    content = path.read_text()
    assert "hf_second" in content
    assert "hf_first" not in content
    assert content.count("[agent]") == 1


def test_save_primary_writes_token_file(tmp_path):
    path = tmp_path / "nested" / "token"
    result = save_primary("hf_secret", token_path=path)
    assert result == path
    assert path.read_text() == "hf_secret\n"
    assert mode_of(path) == 0o600


def test_save_primary_defaults_under_hf_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert save_primary("hf_secret") == tmp_path / "token"


def test_save_env_creates_file(tmp_path):
    path = tmp_path / ".env"
    save_env("hf_secret", path)
    assert path.read_text() == "HF_TOKEN=hf_secret\n"
    assert mode_of(path) == 0o600


def test_save_env_replaces_existing_token_line(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OTHER=1\nHF_TOKEN=hf_old\nMORE=2\n")
    save_env("hf_new", path)
    assert path.read_text() == "OTHER=1\nMORE=2\nHF_TOKEN=hf_new\n"
