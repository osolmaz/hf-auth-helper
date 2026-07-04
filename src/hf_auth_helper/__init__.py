"""Safe, scoped Hugging Face authentication for agents."""

from hf_auth_helper.prefill import build_prefill_url
from hf_auth_helper.scopes import ScopeViolation, TokenReport, evaluate_whoami

__all__ = [
    "ScopeViolation",
    "TokenReport",
    "build_prefill_url",
    "evaluate_whoami",
]
