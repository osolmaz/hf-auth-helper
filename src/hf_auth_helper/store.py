"""Store a verified token where the user chose.

Three destinations, all files the ``hf`` CLI or agent processes already
read: a named profile in ``stored_tokens`` (activate with ``hf auth
switch``), the primary token file, or an ``HF_TOKEN=`` line in an env file.
Written files are readable by the owner only.
"""

import configparser
import os
from pathlib import Path

TOKEN_FILE_MODE = 0o600


def hf_home() -> Path:
    """The directory the ``hf`` CLI keeps its token files in."""
    home = os.environ.get("HF_HOME")
    return Path(home) if home else Path.home() / ".cache" / "huggingface"


def find_existing_token() -> str | None:
    """An already-configured Hub token, if the machine has one.

    Checks ``HF_TOKEN`` and then the ``hf`` CLI's active token file. Used
    only to *read* account facts (like organization names) during setup —
    never stored or displayed.
    """
    env_token = os.environ.get("HF_TOKEN", "").strip()
    if env_token:
        return env_token
    token_path = hf_home() / "token"
    if token_path.is_file():
        return token_path.read_text(encoding="utf-8").strip() or None
    return None


class _CaseSensitiveParser(configparser.ConfigParser):
    """ConfigParser that leaves option names (like ``hf_token``) untouched."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def save_profile(token: str, name: str, stored_tokens_path: Path | None = None) -> Path:
    """Add or update a named token profile for ``hf auth switch``."""
    path = stored_tokens_path or hf_home() / "stored_tokens"
    profiles = _CaseSensitiveParser()
    if path.exists():
        profiles.read(path)
    if not profiles.has_section(name):
        profiles.add_section(name)
    profiles.set(name, "hf_token", token)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        profiles.write(handle)
    path.chmod(TOKEN_FILE_MODE)
    return path


def save_primary(token: str, token_path: Path | None = None) -> Path:
    """Make ``token`` the active ``hf`` CLI token."""
    path = token_path or hf_home() / "token"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{token}\n", encoding="utf-8")
    path.chmod(TOKEN_FILE_MODE)
    return path


def save_env(token: str, env_path: Path) -> Path:
    """Write ``HF_TOKEN=…`` into ``env_path``, replacing any existing line."""
    lines = []
    if env_path.exists():
        lines = [
            line
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("HF_TOKEN=")
        ]
    lines.append(f"HF_TOKEN={token}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_path.chmod(TOKEN_FILE_MODE)
    return env_path
