"""General utility and log-file helpers, moved from app.py (Phase 7 refactor, no behavior change).

- _ts: current local time as an "HH:MM:SS" string, used to timestamp log lines.
- write_log_lines: write a list of log lines to a log file, silently ignoring
  write failures (matches the previous App._write_log behavior).
"""
import datetime
from pathlib import Path


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def write_log_lines(path, log_lines):
    try:
        Path(path).write_text("\n".join(log_lines))
    except Exception:
        pass
