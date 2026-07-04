"""Tests for the CLI entry point."""

import json

from hf_auth_helper.cli import main


def test_prints_prefill_url(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("https://huggingface.co/settings/tokens/new?")


def test_json_output_with_org_and_gated(capsys):
    assert main(["--org", "someorg", "--gated", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "orgs=someorg" in payload["prefill_url"]
    assert "canReadGatedRepos=true" in payload["prefill_url"]
