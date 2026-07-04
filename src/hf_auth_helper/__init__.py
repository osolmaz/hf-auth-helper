"""Safe, scoped Hugging Face authentication for agents."""

from hf_auth_helper.prefill import (
    OPTIONS,
    build_prefill_url,
    recommended_selection,
    summarize,
)
from hf_auth_helper.scopes import (
    ScopeDiff,
    ScopeViolation,
    TokenReport,
    diff_scopes,
    evaluate_whoami,
)
from hf_auth_helper.store import (
    ProfileExistsError,
    save_env,
    save_primary,
    save_profile,
)
from hf_auth_helper.verify import VerificationError, verify_token

__all__ = [
    "OPTIONS",
    "ProfileExistsError",
    "ScopeDiff",
    "ScopeViolation",
    "TokenReport",
    "VerificationError",
    "build_prefill_url",
    "diff_scopes",
    "evaluate_whoami",
    "recommended_selection",
    "save_env",
    "save_primary",
    "save_profile",
    "summarize",
    "verify_token",
]
