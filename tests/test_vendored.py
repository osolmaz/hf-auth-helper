"""Smoke test for the vendored questionary stack."""

from hf_auth_helper.vendored import load_questionary
from hf_auth_helper.wizard import PromptBackend


def test_vendored_questionary_imports_and_matches_protocol():
    questionary = load_questionary()
    assert questionary.__name__ == "questionary"
    assert "vendor" in str(questionary.__file__)
    assert isinstance(questionary, PromptBackend)
