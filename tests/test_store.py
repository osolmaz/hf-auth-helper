"""Tests for the registry storage model.

The invariant under test: no token value is ever destroyed — after any
sequence of store operations, the set of token values on disk never
shrinks.
"""

import stat

import pytest

from hf_auth_helper.store import (
    ProfileExistsError,
    find_existing_token,
    find_profile_name,
    hf_home,
    read_active_token,
    read_profiles,
    save_env,
    save_primary,
    save_profile,
    unique_profile_name,
)


def mode_of(path):
    return stat.S_IMODE(path.stat().st_mode)


def all_values(stored_tokens_path):
    return set(read_profiles(stored_tokens_path).values())


def test_hf_home_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "custom"))
    assert hf_home() == tmp_path / "custom"


def test_hf_home_defaults_to_cache(monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    assert str(hf_home()).endswith(".cache/huggingface")


def test_find_existing_token_prefers_env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_from_env")
    assert find_existing_token() == "hf_from_env"


def test_find_existing_token_reads_token_file(monkeypatch):
    (hf_home()).mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_from_file\n")
    assert find_existing_token() == "hf_from_file"


def test_read_active_token_ignores_env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_from_env")
    assert read_active_token() is None
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("hf_pointer\n")
    assert read_active_token() == "hf_pointer"


def test_find_existing_token_handles_absence():
    assert find_existing_token() is None
    hf_home().mkdir(parents=True, exist_ok=True)
    (hf_home() / "token").write_text("  \n")
    assert find_existing_token() is None


def test_save_profile_creates_registry(tmp_path):
    path = tmp_path / "stored_tokens"
    result = save_profile("hf_value", "agent", stored_tokens_path=path)
    assert result == path
    assert read_profiles(path) == {"agent": "hf_value"}
    assert "hf_token = hf_value" in path.read_text()
    assert mode_of(path) == 0o600


def test_save_profile_preserves_other_profiles(tmp_path):
    path = tmp_path / "stored_tokens"
    save_profile("hf_old", "existing", stored_tokens_path=path)
    save_profile("hf_new", "agent", stored_tokens_path=path)
    assert read_profiles(path) == {"existing": "hf_old", "agent": "hf_new"}


def test_save_profile_same_value_is_idempotent(tmp_path):
    path = tmp_path / "stored_tokens"
    save_profile("hf_value", "agent", stored_tokens_path=path)
    save_profile("hf_value", "agent", stored_tokens_path=path)
    assert read_profiles(path) == {"agent": "hf_value"}


def test_save_profile_collision_raises_and_destroys_nothing(tmp_path):
    path = tmp_path / "stored_tokens"
    save_profile("hf_first", "agent", stored_tokens_path=path)
    before = all_values(path)
    with pytest.raises(ProfileExistsError) as info:
        save_profile("hf_second", "agent", stored_tokens_path=path)
    assert info.value.name == "agent"
    assert all_values(path) == before


def test_save_profile_replace_supersedes_by_name(tmp_path):
    path = tmp_path / "stored_tokens"
    save_profile("hf_first", "agent", stored_tokens_path=path)
    save_profile("hf_second", "agent", stored_tokens_path=path, replace=True)
    assert read_profiles(path) == {"agent": "hf_second"}


def test_find_profile_name_by_value(tmp_path):
    path = tmp_path / "stored_tokens"
    save_profile("hf_value", "agent", stored_tokens_path=path)
    assert find_profile_name("hf_value", stored_tokens_path=path) == "agent"
    assert find_profile_name("hf_other", stored_tokens_path=path) is None


def test_unique_profile_name_suffixes(tmp_path):
    path = tmp_path / "stored_tokens"
    assert unique_profile_name("agent", stored_tokens_path=path) == "agent"
    save_profile("hf_1", "agent", stored_tokens_path=path)
    assert unique_profile_name("agent", stored_tokens_path=path) == "agent-2"
    save_profile("hf_2", "agent-2", stored_tokens_path=path)
    assert unique_profile_name("agent", stored_tokens_path=path) == "agent-3"


def test_save_primary_registers_profile_and_writes_pointer(tmp_path):
    registry = tmp_path / "stored_tokens"
    pointer = tmp_path / "token"
    save_primary("hf_value", "agent", stored_tokens_path=registry, token_path=pointer)
    assert read_profiles(registry) == {"agent": "hf_value"}
    assert pointer.read_text() == "hf_value\n"
    assert mode_of(pointer) == 0o600


def test_save_primary_collision_leaves_pointer_untouched(tmp_path):
    registry = tmp_path / "stored_tokens"
    pointer = tmp_path / "token"
    save_profile("hf_first", "agent", stored_tokens_path=registry)
    with pytest.raises(ProfileExistsError):
        save_primary("hf_second", "agent", stored_tokens_path=registry, token_path=pointer)
    assert not pointer.exists()
    assert read_profiles(registry) == {"agent": "hf_first"}


def test_save_primary_defaults_under_hf_home():
    path = save_primary("hf_value", "agent")
    assert path == hf_home() / "token"
    assert read_profiles() == {"agent": "hf_value"}


def test_save_env_creates_file(tmp_path):
    path = tmp_path / ".env"
    result, replaced = save_env("hf_value", path)
    assert result == path
    assert replaced is False
    assert path.read_text() == "HF_TOKEN=hf_value\n"
    assert mode_of(path) == 0o600


def test_save_env_replaces_existing_token_line(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OTHER=1\nHF_TOKEN=hf_old\nMORE=2\n")
    _, replaced = save_env("hf_new", path)
    assert replaced is True
    assert path.read_text() == "OTHER=1\nMORE=2\nHF_TOKEN=hf_new\n"
