"""Shared test isolation.

Every test runs with HOME and HF_HOME pointed into a temp directory, so no
test — and no mutant during mutation testing, which once rewrote the
"HF_HOME" lookup and made a test write to the real token file — can touch
the developer's actual Hugging Face credentials. HF_TOKEN is cleared for
the same reason.
"""

import pytest


@pytest.fixture(autouse=True)
def isolate_credential_files(monkeypatch, tmp_path):
    home = tmp_path / "isolated-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HF_HOME", str(home / "hf"))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    # Relative paths (e.g. an env-file answer like "agent.env") must land
    # in the test sandbox, never in the repository working tree.
    monkeypatch.chdir(tmp_path)
