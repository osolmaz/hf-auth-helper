"""Safe, scoped Hugging Face authentication for agents."""

from hf_auth_helper.prefill import build_prefill_url
from hf_auth_helper.scopes import ScopeViolation, TokenReport, evaluate_whoami
from hf_auth_helper.store import save_env, save_primary, save_profile
from hf_auth_helper.verify import VerificationError, verify_token

__all__ = [
    "ScopeViolation",
    "TokenReport",
    "VerificationError",
    "build_prefill_url",
    "evaluate_whoami",
    "save_env",
    "save_primary",
    "save_profile",
    "verify_token",
]
