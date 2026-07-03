"""Settings load/save helpers, moved from app.py (Phase 1 refactor, no behavior change).

- load_settings: read settings.json, falling back to the same defaults app.py used.
- save_settings: write a dict to settings.json as indented JSON.
"""
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {
        "buffer_key": "", "buffer_channel_id": "", "post_time": "18:00",
        "ai_speed_mode": "Balanced",
        "ai_model": "qwen3:14b", "preferred_browser": "chrome",
    }


def save_settings(d: dict):
    SETTINGS_PATH.write_text(json.dumps(d, indent=2))
