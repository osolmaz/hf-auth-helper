"""Store a verified token where the user chose.

The ``hf`` CLI's storage is a registry: ``stored_tokens`` holds named
credentials, and the ``token`` file is a pointer selecting the active
one. This module maintains that model under one invariant: every token
value that passes through the tool has a name in the registry, and no
credential value is ever destroyed — only superseded by name. Env files
are exports and sit outside the registry. Written files are readable by
the owner only.
"""

import configparser
import os
from pathlib import Path

TOKEN_FILE_MODE = 0o600


class ProfileExistsError(Exception):
    """A profile with this name already holds a different token value."""

    def __init__(self, name: str) -> None:
        super().__init__(f"profile '{name}' already exists with a different token")
        self.name = name


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
    return read_active_token()


def read_active_token(token_path: Path | None = None) -> str | None:
    """The value the ``hf`` CLI's active-token pointer file holds, if any."""
    path = token_path or hf_home() / "token"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or None
    return None


def read_profiles(stored_tokens_path: Path | None = None) -> dict[str, str]:
    """All named profiles in the registry, name -> token value."""
    path = stored_tokens_path or hf_home() / "stored_tokens"
    parser = _read_registry(path)
    return {name: parser.get(name, "hf_token", fallback="") for name in parser.sections()}


def find_profile_name(token: str, stored_tokens_path: Path | None = None) -> str | None:
    """The registry name holding this token value, if it is registered."""
    for name, value in read_profiles(stored_tokens_path).items():
        if value == token:
            return name
    return None


def unique_profile_name(
    base: str,
    stored_tokens_path: Path | None = None,
    avoid: tuple[str, ...] = (),
) -> str:
    """``base``, or ``base-2``/``base-3``/… if taken or in ``avoid``."""
    unavailable = set(read_profiles(stored_tokens_path)) | set(avoid)
    if base not in unavailable:
        return base
    suffix = 2
    while f"{base}-{suffix}" in unavailable:
        suffix += 1
    return f"{base}-{suffix}"


def save_profile(
    token: str,
    name: str,
    stored_tokens_path: Path | None = None,
    replace: bool = False,
) -> Path:
    """Register the token under ``name`` in the registry.

    Raises :class:`ProfileExistsError` when the name holds a *different*
    value and ``replace`` is false. Re-saving the same value under the
    same name is idempotent.
    """
    path = stored_tokens_path or hf_home() / "stored_tokens"
    profiles = _read_registry(path)
    if profiles.has_section(name):
        current = profiles.get(name, "hf_token", fallback="")
        if current != token and not replace:
            raise ProfileExistsError(name)
    else:
        profiles.add_section(name)
    profiles.set(name, "hf_token", token)
    _write_owner_only(path, profiles)
    return path


def save_primary(
    token: str,
    name: str,
    stored_tokens_path: Path | None = None,
    token_path: Path | None = None,
    replace: bool = False,
) -> Path:
    """Make ``token`` the active ``hf`` CLI token.

    Registers it as profile ``name`` first — there is no path that writes
    the pointer without the registry entry.
    """
    save_profile(token, name, stored_tokens_path=stored_tokens_path, replace=replace)
    path = token_path or hf_home() / "token"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{token}\n", encoding="utf-8")
    path.chmod(TOKEN_FILE_MODE)
    return path


def save_env(token: str, env_path: Path) -> tuple[Path, bool]:
    """Write ``HF_TOKEN=…`` into ``env_path``; report whether a previous
    ``HF_TOKEN`` line was replaced."""
    lines: list[str] = []
    replaced = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("HF_TOKEN="):
                replaced = True
            else:
                lines.append(line)
    lines.append(f"HF_TOKEN={token}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_path.chmod(TOKEN_FILE_MODE)
    return env_path, replaced


class _CaseSensitiveParser(configparser.ConfigParser):
    """ConfigParser that leaves option names (like ``hf_token``) untouched."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def _read_registry(path: Path) -> _CaseSensitiveParser:
    parser = _CaseSensitiveParser()
    if path.exists():
        parser.read(path)
    return parser


def _write_owner_only(path: Path, profiles: configparser.ConfigParser) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        profiles.write(handle)
    path.chmod(TOKEN_FILE_MODE)
