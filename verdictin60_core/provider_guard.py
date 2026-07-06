"""Centralized safety guard for external AI/cloud/service providers (issue #61).

Every paid or quota-limited provider (NVIDIA NIM today; GitHub/Claude/Codex/
OpenAI or any future connector) should route through this module instead of
retrying blindly:

  1. Call `is_provider_disabled(name)` before making a network request and
     fall back to local/non-AI behavior if it returns True.
  2. Call `report_failure(name, ...)` when a call fails. Quota/billing/
     rate-limit/auth-shaped failures disable the provider for the rest of the
     session (or for a cooldown window, for plain rate limits and timeouts);
     other, unclassified failures do not.
  3. Call `clear_settings_triggered_disables(name)` when the user saves
     Settings, since quota and auth disables are documented to last "until
     app restart or settings change".

A bare request timeout gets its own short cooldown (see TIMEOUT below):
a single slow/unreachable provider shouldn't be retried again a few seconds
later by the next step of the same workflow (e.g. Research Hub's post draft
then caption generation, issue #67) only to time out a second time.

This module never logs anything and never receives API keys/tokens/headers —
callers must only ever pass sanitized status codes or generic error text
(see verdictin60_core/ai.py's NvidiaAPIError, which never includes the key).
"""
import re
import time

from verdictin60_core.settings import load_settings

RATE_LIMIT = "rate_limit"
QUOTA = "quota"
AUTH = "auth"
TIMEOUT = "timeout"
UNKNOWN = "unknown"

# Rate limits and timeouts recover on their own after a cooldown; quota/
# billing and auth failures stay disabled until the user restarts the app or
# changes settings (see clear_settings_triggered_disables).
RATE_LIMIT_COOLDOWN_SECONDS = 10 * 60

# Short on purpose — long enough that the next step of the *same* workflow
# (e.g. post draft then caption generation) skips straight to the local
# fallback instead of waiting out a second identical timeout, short enough
# that the next unrelated investigation still gets a fresh cloud attempt.
TIMEOUT_COOLDOWN_SECONDS = 2 * 60

# How many consecutive classified failures are required before a provider is
# disabled when the user has turned off "disable after first error".
STRIKES_BEFORE_DISABLE = 3

# provider name -> {"category": str, "disabled_until": float | None}
_STATE = {}
# provider name -> consecutive classified-failure count (only consulted when
# "disable after first error" is off)
_STRIKES = {}

_RATE_LIMIT_RE = re.compile(
    r"\b429\b|\b503\b|rate.?limit|too many requests|abuse[ _-]?protect|"
    r"slow down|model.{0,20}unavailable|service.{0,20}unavailable",
    re.I,
)
_QUOTA_RE = re.compile(
    r"\b402\b|quota|insufficient.{0,10}credit|out of credit|billing|"
    r"payment required|free tier|account limit",
    re.I,
)
_AUTH_RE = re.compile(
    r"\b401\b|\b403\b|unauthorized|forbidden|access denied|invalid api key|"
    r"invalid.{0,10}key|token expired|expired token",
    re.I,
)
_TIMEOUT_RE = re.compile(r"timed out|timeout", re.I)


def classify_failure(exc_or_message=None, status_code=None) -> str:
    """Classify a provider failure as rate_limit / quota / auth / timeout / unknown.

    Prefer `status_code` (authoritative, e.g. an HTTP status) when the caller
    has one; otherwise fall back to pattern-matching the message text. Never
    logs or stores the input — only inspects it in memory."""
    if status_code is not None:
        if status_code == 429:
            return RATE_LIMIT
        if status_code == 402:
            return QUOTA
        if status_code in (401, 403):
            return AUTH
        if status_code == 503:
            return RATE_LIMIT

    text = str(exc_or_message or "")
    if _QUOTA_RE.search(text):
        return QUOTA
    if _RATE_LIMIT_RE.search(text):
        return RATE_LIMIT
    if _AUTH_RE.search(text):
        return AUTH
    if _TIMEOUT_RE.search(text):
        return TIMEOUT
    return UNKNOWN


def _guard_enabled() -> bool:
    return bool(load_settings().get("cloud_spending_guard", True))


def _disable_after_first_error() -> bool:
    return bool(load_settings().get("disable_provider_after_first_error", True))


def is_provider_disabled(provider: str) -> bool:
    """True if `provider` should not be called right now."""
    entry = _STATE.get(provider)
    if not entry:
        return False
    until = entry.get("disabled_until")
    if until is not None and time.time() >= until:
        _STATE.pop(provider, None)
        return False
    return True


def provider_status(provider: str) -> str:
    """Human-readable status for a read-only Settings provider list."""
    entry = _STATE.get(provider)
    if not entry or not is_provider_disabled(provider):
        return "Active"
    category = entry.get("category")
    if category == RATE_LIMIT:
        return "Rate limited"
    if category == QUOTA:
        return "Quota reached"
    if category == TIMEOUT:
        return "Timed out — retrying shortly"
    return "Disabled"


def report_failure(provider: str, exc_or_message=None, status_code=None) -> str:
    """Record a provider failure. Disables the provider per the safety
    settings if the failure classifies as rate_limit/quota/auth/timeout.
    Returns the classified category (callers may ignore it)."""
    category = classify_failure(exc_or_message, status_code=status_code)
    if category == UNKNOWN or not _guard_enabled():
        return category

    if not _disable_after_first_error():
        strikes = _STRIKES.get(provider, 0) + 1
        _STRIKES[provider] = strikes
        if strikes < STRIKES_BEFORE_DISABLE:
            return category

    _STRIKES.pop(provider, None)
    if category == RATE_LIMIT:
        until = time.time() + RATE_LIMIT_COOLDOWN_SECONDS
    elif category == TIMEOUT:
        until = time.time() + TIMEOUT_COOLDOWN_SECONDS
    else:
        until = None
    _STATE[provider] = {"category": category, "disabled_until": until}
    return category


def report_success(provider: str):
    """Clear strike bookkeeping after a successful call."""
    _STRIKES.pop(provider, None)


def clear_settings_triggered_disables(provider: str):
    """Clear a QUOTA or AUTH disable for `provider`. Call this when the user
    saves Settings — those two cooldowns are documented to last "until app
    restart or settings change". Rate-limit cooldowns are strictly time-based
    and are intentionally left alone here."""
    entry = _STATE.get(provider)
    if entry and entry.get("category") in (QUOTA, AUTH):
        _STATE.pop(provider, None)
        _STRIKES.pop(provider, None)


def reset_provider(provider: str):
    """Unconditionally clear all guard state for `provider` (e.g. in tests)."""
    _STATE.pop(provider, None)
    _STRIKES.pop(provider, None)


def reset_all():
    _STATE.clear()
    _STRIKES.clear()
