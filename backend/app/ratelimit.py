"""In-memory failed-login throttle.

Keeps a small, self-pruning record of recent *failed* login attempts keyed by
``(email, client-ip)``. Successful logins never accumulate, so legitimate users
are unaffected; an attacker hammering a single account/line is locked out after
``login_max_failures`` attempts for ``login_lockout_seconds``.

State is process-local (no Redis dependency) — adequate for this single-server
school deployment and far better than no throttle at all.
"""
import time

from .config import settings

# key -> list[float] of failure timestamps (monotonic-ish wall clock)
_failures: dict[str, list[float]] = {}
# key -> epoch second the lock lifts
_locked_until: dict[str, float] = {}


def _key(email: str, ip: str) -> str:
    return f"{email.strip().lower()}|{ip}"


def is_locked(email: str, ip: str) -> int:
    """Seconds remaining on an active lock for this (email, ip), else 0."""
    key = _key(email, ip)
    until = _locked_until.get(key)
    if until is None:
        return 0
    remaining = until - time.time()
    if remaining <= 0:
        _locked_until.pop(key, None)
        _failures.pop(key, None)
        return 0
    return int(remaining) + 1


def record_failure(email: str, ip: str) -> None:
    """Note a failed attempt; arm a lock once the threshold is reached."""
    key = _key(email, ip)
    now = time.time()
    window = settings.login_failure_window_seconds
    hits = [t for t in _failures.get(key, []) if now - t < window]
    hits.append(now)
    _failures[key] = hits
    if len(hits) >= settings.login_max_failures:
        _locked_until[key] = now + settings.login_lockout_seconds


def reset(email: str, ip: str) -> None:
    """Clear all failure state for this (email, ip) after a successful login."""
    key = _key(email, ip)
    _failures.pop(key, None)
    _locked_until.pop(key, None)
