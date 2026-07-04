"""Interactive steps of the setup, backed by questionary.

Every prompt goes through the :class:`PromptBackend` protocol — the real
backend is the vendored questionary module, tests inject fakes. Answers
arrive as ``object`` (questionary returns ``None`` on ctrl-c) and are
narrowed here before anyone uses them.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

ENTER_MANUALLY = "Enter another organization manually…"


class SetupCancelled(Exception):  # noqa: N818 -- a control-flow signal, not an error
    """The user cancelled the setup (ctrl-c) mid-prompt."""


class Question(Protocol):
    """The subset of a questionary question the wizard uses."""

    def ask(self) -> object: ...


@runtime_checkable
class PromptBackend(Protocol):
    """The subset of the questionary API the wizard uses."""

    def confirm(self, message: str, default: bool = ...) -> Question: ...

    def checkbox(self, message: str, choices: Sequence[str]) -> Question: ...

    def text(self, message: str, default: str = ...) -> Question: ...

    def select(self, message: str, choices: Sequence[str]) -> Question: ...


def _answer(question: Question) -> object:
    """Return the prompt's answer; questionary yields None on ctrl-c."""
    answer = question.ask()
    if answer is None:
        raise SetupCancelled
    return answer


def ask_use_recommended(prompts: PromptBackend) -> bool:
    """Step 1: accept the recommended selection, or customize."""
    answer = _answer(
        prompts.confirm("Use the recommended access settings for the agent?", default=True)
    )
    return answer is True


def customize_selection(
    prompts: PromptBackend,
    questions: Sequence[tuple[str, str]],
) -> frozenset[str]:
    """Step 3: one yes/no per optional capability; ``(key, question)`` pairs."""
    enabled = set()
    for key, question in questions:
        if _answer(prompts.confirm(question, default=True)) is True:
            enabled.add(key)
    return frozenset(enabled)


def ask_open_browser(prompts: PromptBackend, default: bool) -> bool:
    """Ask before ever launching a browser (remote-first)."""
    answer = _answer(
        prompts.confirm("Open this page in a browser on this machine?", default=default)
    )
    return answer is True


def confirm_replace_profile(prompts: PromptBackend, name: str) -> bool:
    """Ask before overwriting an existing profile with a different value."""
    answer = _answer(
        prompts.confirm(f"Profile '{name}' already exists — replace it?", default=False)
    )
    return answer is True


def choose_orgs(prompts: PromptBackend, detected: tuple[str, ...]) -> tuple[str, ...]:
    """Ask which organizations the agent token should extend to."""
    wants_orgs = _answer(
        prompts.confirm(
            "Grant the agent propose-only access to organizations as well?",
            default=bool(detected),
        )
    )
    if wants_orgs is not True:
        return ()
    chosen = _choose_detected(prompts, detected) if detected else [ENTER_MANUALLY]
    if ENTER_MANUALLY in chosen:
        chosen = [org for org in chosen if org != ENTER_MANUALLY]
        chosen.extend(_ask_manual_orgs(prompts, exclude=chosen))
    return tuple(chosen)


def _choose_detected(prompts: PromptBackend, detected: tuple[str, ...]) -> list[str]:
    answer = _answer(
        prompts.checkbox(
            "Select organizations (space to toggle, enter to confirm):",
            choices=[*detected, ENTER_MANUALLY],
        )
    )
    return _string_list(answer)


def _ask_manual_orgs(prompts: PromptBackend, exclude: list[str]) -> list[str]:
    manual: list[str] = []
    while True:
        answer = _answer(prompts.text("Organization name (leave empty to finish):"))
        name = answer.strip() if isinstance(answer, str) else ""
        if not name:
            return manual
        if name not in manual and name not in exclude:
            manual.append(name)


def choose_destination(prompts: PromptBackend) -> str:
    """Ask where the verified token should be stored."""
    answer = _answer(
        prompts.select(
            "Where should the token go?",
            choices=[
                "Named hf CLI profile (activate with: hf auth switch)",
                "Primary hf CLI token",
                "Env file (HF_TOKEN=…)",
            ],
        )
    )
    text = answer if isinstance(answer, str) else ""
    if text.startswith("Primary"):
        return "primary"
    if text.startswith("Env"):
        return "env"
    return "profile"


def ask_profile_name(prompts: PromptBackend, suggested: str) -> str:
    """Ask for the profile name, offering a suggestion."""
    answer = _answer(prompts.text("Profile name:", default=suggested))
    name = answer.strip() if isinstance(answer, str) else ""
    return name or suggested


def ask_env_path(prompts: PromptBackend) -> str:
    """Ask which env file to write HF_TOKEN into."""
    answer = _answer(prompts.text("Env file path:", default=".env"))
    path = answer.strip() if isinstance(answer, str) else ""
    return path or ".env"


def _string_list(answer: object) -> list[str]:
    if not isinstance(answer, Sequence) or isinstance(answer, str):
        return []
    return [item for item in answer if isinstance(item, str)]
