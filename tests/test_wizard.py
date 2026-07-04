"""Tests for the interactive wizard steps, using a fake prompt backend."""

import pytest

from hf_auth_helper.wizard import (
    ENTER_MANUALLY,
    ENV_FILE_CHOICE,
    MACHINE_LOGIN_CHOICE,
    SetupCancelled,
    ask_env_path,
    ask_open_browser,
    ask_profile_name,
    ask_token,
    ask_use_recommended,
    choose_destination,
    choose_orgs,
    confirm_replace_profile,
    customize_selection,
)


class FakeQuestion:
    def __init__(self, answer):
        self.answer = answer

    def ask(self):
        return self.answer


class FakeBackend:
    """Replays scripted answers and records every prompt."""

    def __init__(self, confirms=(), checkboxes=(), texts=(), selects=(), passwords=()):
        self.confirms = list(confirms)
        self.checkboxes = list(checkboxes)
        self.texts = list(texts)
        self.selects = list(selects)
        self.passwords = list(passwords)
        self.seen_choices = []

    def confirm(self, message, default=False):
        return FakeQuestion(self.confirms.pop(0))

    def checkbox(self, message, choices):
        self.seen_choices.append(list(choices))
        return FakeQuestion(self.checkboxes.pop(0))

    def text(self, message, default=""):
        return FakeQuestion(self.texts.pop(0))

    def select(self, message, choices):
        self.seen_choices.append(list(choices))
        return FakeQuestion(self.selects.pop(0))

    def password(self, message):
        return FakeQuestion(self.passwords.pop(0))


def test_declining_orgs_returns_nothing():
    backend = FakeBackend(confirms=[False])
    assert choose_orgs(backend, ("someorg",)) == ()


def test_ctrl_c_cancels_at_any_prompt():
    with pytest.raises(SetupCancelled):
        choose_orgs(FakeBackend(confirms=[None]), ("someorg",))
    with pytest.raises(SetupCancelled):
        choose_orgs(FakeBackend(confirms=[True], checkboxes=[None]), ("someorg",))
    with pytest.raises(SetupCancelled):
        choose_orgs(FakeBackend(confirms=[True], texts=[None]), ())
    with pytest.raises(SetupCancelled):
        choose_destination(FakeBackend(selects=[None]))
    with pytest.raises(SetupCancelled):
        ask_profile_name(FakeBackend(texts=[None]), "suggested")
    with pytest.raises(SetupCancelled):
        ask_env_path(FakeBackend(texts=[None]))


def test_detected_orgs_are_offered_with_manual_escape_hatch():
    backend = FakeBackend(confirms=[True], checkboxes=[["someorg", "otherorg"]])
    assert choose_orgs(backend, ("someorg", "otherorg")) == ("someorg", "otherorg")
    assert backend.seen_choices == [["someorg", "otherorg", ENTER_MANUALLY]]


def test_manual_entry_extends_detected_selection():
    backend = FakeBackend(
        confirms=[True],
        checkboxes=[["someorg", ENTER_MANUALLY]],
        texts=["neworg", "  ", ""],
    )
    assert choose_orgs(backend, ("someorg",)) == ("someorg", "neworg")


def test_manual_entry_skips_duplicates():
    backend = FakeBackend(
        confirms=[True],
        checkboxes=[["someorg", ENTER_MANUALLY]],
        texts=["someorg", "neworg", "neworg", ""],
    )
    assert choose_orgs(backend, ("someorg",)) == ("someorg", "neworg")


def test_no_detected_orgs_goes_straight_to_manual():
    backend = FakeBackend(confirms=[True], texts=["someorg", ""])
    assert choose_orgs(backend, ()) == ("someorg",)
    assert backend.seen_choices == []


def test_choose_destination_maps_selections():
    assert choose_destination(FakeBackend(selects=[MACHINE_LOGIN_CHOICE])) == "primary"
    assert choose_destination(FakeBackend(selects=[ENV_FILE_CHOICE])) == "env"
    backend = FakeBackend(selects=[MACHINE_LOGIN_CHOICE])
    choose_destination(backend)
    assert backend.seen_choices == [[MACHINE_LOGIN_CHOICE, ENV_FILE_CHOICE]]


def test_ask_profile_name_falls_back_to_suggestion():
    assert ask_profile_name(FakeBackend(texts=["custom"]), "suggested") == "custom"
    assert ask_profile_name(FakeBackend(texts=["  "]), "suggested") == "suggested"


def test_ask_env_path_defaults():
    assert ask_env_path(FakeBackend(texts=["service/.env"])) == "service/.env"
    assert ask_env_path(FakeBackend(texts=["  "])) == ".env"


def test_ask_use_recommended():
    assert ask_use_recommended(FakeBackend(confirms=[True])) is True
    assert ask_use_recommended(FakeBackend(confirms=[False])) is False
    with pytest.raises(SetupCancelled):
        ask_use_recommended(FakeBackend(confirms=[None]))


def test_customize_selection_collects_accepted_keys():
    questions = [("gated", "Gated?"), ("billing", "Billing?"), ("collections", "Collections?")]
    backend = FakeBackend(confirms=[True, False, True])
    assert customize_selection(backend, questions) == frozenset({"gated", "collections"})


def test_customize_selection_cancel_mid_series():
    with pytest.raises(SetupCancelled):
        customize_selection(FakeBackend(confirms=[True, None]), [("a", "A?"), ("b", "B?")])


def test_ask_open_browser_uses_default_and_answer():
    assert ask_open_browser(FakeBackend(confirms=[True]), default=False) is True
    assert ask_open_browser(FakeBackend(confirms=[False]), default=True) is False
    with pytest.raises(SetupCancelled):
        ask_open_browser(FakeBackend(confirms=[None]), default=True)


def test_confirm_replace_profile():
    assert confirm_replace_profile(FakeBackend(confirms=[True]), "agent") is True
    assert confirm_replace_profile(FakeBackend(confirms=[False]), "agent") is False
    with pytest.raises(SetupCancelled):
        confirm_replace_profile(FakeBackend(confirms=[None]), "agent")


def test_ask_token_strips_and_cancels():
    assert ask_token(FakeBackend(passwords=["  hf_x  "])) == "hf_x"
    with pytest.raises(SetupCancelled):
        ask_token(FakeBackend(passwords=[None]))
