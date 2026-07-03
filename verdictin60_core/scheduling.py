"""Post date/time formatting helpers, moved from app.py (Phase 1 refactor, no behavior change).

- next_post_datetime: next occurrence of a "HH:MM" local time, as a UTC-aware datetime.
- batch_post_datetime: tomorrow + offset_days at a "HH:MM" local time, as a UTC-aware datetime.
- _date_at_post_time: a given date's calendar day at a "HH:MM" local time, as a UTC-aware datetime.
"""
import datetime


def next_post_datetime(time_str: str) -> datetime.datetime:
    try:
        h, m = [int(x) for x in time_str.strip().split(":")]
    except Exception:
        h, m = 18, 0
    now = datetime.datetime.now()
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now:
        candidate += datetime.timedelta(days=1)
    aware = candidate.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)
    return aware.astimezone(datetime.timezone.utc)


def batch_post_datetime(time_str: str, offset_days: int) -> datetime.datetime:
    """tomorrow + offset_days at post_time, as UTC-aware datetime."""
    try:
        h, m = [int(x) for x in time_str.strip().split(":")]
    except Exception:
        h, m = 18, 0
    base = datetime.datetime.now() + datetime.timedelta(days=1 + offset_days)
    candidate = base.replace(hour=h, minute=m, second=0, microsecond=0)
    aware = candidate.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)
    return aware.astimezone(datetime.timezone.utc)


def _date_at_post_time(base_date: datetime.datetime, time_str: str) -> datetime.datetime:
    """Return base_date's calendar day at post_time (local), as UTC-aware datetime."""
    try:
        h, m = [int(x) for x in time_str.strip().split(":")]
    except Exception:
        h, m = 18, 0
    local_tz = datetime.datetime.now().astimezone().tzinfo
    local_base = base_date.astimezone(local_tz)
    candidate = local_base.replace(hour=h, minute=m, second=0, microsecond=0)
    return candidate.astimezone(datetime.timezone.utc)
