"""Filename/display-name conversion helpers, moved from app.py (Phase 1 refactor, no behavior change).

- name_to_filename: turn a free-typed case title into a "Word-Word" filename stem.
- filename_to_display: turn a "Word-Word" filename stem back into a readable title.
"""
import re


def name_to_filename(raw: str) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", raw)
    if not words:
        return "Untitled-Case"
    return "-".join(w.capitalize() for w in words)


def filename_to_display(fname: str) -> str:
    return fname.replace("-", " ")
