"""Rule-based Recovery Assistant helpers, moved from app.py (Phase 7 refactor, no behavior change).

- log_recovery_event: append an approved/declined repair attempt to the local
  recovery history log (recovery-history.json).
- scan_recovery_health: run a free, local rule-based diagnostic scan across
  the downloader, ffmpeg, assets, local AI, Internet Archive, Buffer, and
  storage areas, returning a list of issue dicts for the Recovery tab.
- recovery_plain_message: turn a raw error string into a plain-language
  explanation for the Recovery Assistant.
- _recovery_history / _recovery_issue: low-level history-read and
  issue-dict-building helpers used by the functions above.
"""
import json
import os
import shutil
import subprocess
import datetime
from pathlib import Path

from verdictin60_core.settings import load_settings
from verdictin60_core.imports import ytdlp_cmd
from verdictin60_core.ai import get_ai_model

ROOT_DIR       = Path(__file__).resolve().parent.parent
ASSETS_DIR     = ROOT_DIR / "assets"
OUTPUT_DIR     = ROOT_DIR / "finished-reels"
CTA_PATH       = ASSETS_DIR / "cta-endcard.mp4"
VOICEOVER_PATH = ASSETS_DIR / "voiceover.mp3"
LOGO_PATH      = ASSETS_DIR / "logo.png"
RECOVERY_HISTORY_PATH = ROOT_DIR / "recovery-history.json"

FFMPEG  = shutil.which("ffmpeg")  or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


def _recovery_history() -> list:
    if RECOVERY_HISTORY_PATH.exists():
        try:
            data = json.loads(RECOVERY_HISTORY_PATH.read_text())
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def log_recovery_event(problem: str, rule: str, approved: bool,
                       result: str, verification: str):
    history = _recovery_history()
    history.append({
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "problem": problem,
        "rule": rule,
        "approved": approved,
        "result": result,
        "verification": verification,
    })
    RECOVERY_HISTORY_PATH.write_text(json.dumps(history[-300:], indent=2))


def _recovery_issue(area: str, status: str, severity: str, problem: str,
                    why: str, repair: str = "", action: str = "") -> dict:
    return {
        "area": area,
        "status": status,
        "severity": severity,
        "problem": problem,
        "why": why,
        "repair": repair,
        "action": action,
    }


def scan_recovery_health() -> list:
    """Run a free, local rule-based diagnostic scan."""
    issues = []
    s = load_settings()

    # Downloader
    try:
        r = subprocess.run(ytdlp_cmd(["--version"]), capture_output=True, text=True, timeout=8)
        if r.returncode == 0:
            issues.append(_recovery_issue(
                "Downloader", "Healthy", "ok",
                "Video downloader is available.",
                f"yt-dlp responded successfully ({r.stdout.strip() or 'installed'})."
            ))
        else:
            issues.append(_recovery_issue(
                "Downloader", "Attention Required", "warning",
                "The video downloader did not start correctly.",
                "The app needs yt-dlp to import reels from links.",
                "Show the install option in URL Import.",
                "show_ytdlp_install",
            ))
    except Exception:
        issues.append(_recovery_issue(
            "Downloader", "Attention Required", "warning",
            "The video downloader is missing or unavailable.",
            "The app needs yt-dlp before it can download reels from URLs.",
            "Show the install option in URL Import.",
            "show_ytdlp_install",
        ))

    # FFmpeg
    ffmpeg_ok = Path(FFMPEG).exists() and os.access(FFMPEG, os.X_OK)
    ffprobe_ok = Path(FFPROBE).exists() and os.access(FFPROBE, os.X_OK)
    if ffmpeg_ok and ffprobe_ok:
        issues.append(_recovery_issue(
            "FFmpeg", "Healthy", "ok",
            "Video processing tools are available.",
            "FFmpeg and FFprobe are installed and executable."
        ))
    else:
        issues.append(_recovery_issue(
            "FFmpeg", "Attention Required", "warning",
            "Video processing tools are missing.",
            "The app needs FFmpeg and FFprobe to prepare videos for Buffer.",
            "Open Settings and install FFmpeg manually if needed.",
            "open_settings",
        ))

    # Assets
    missing_assets = []
    for label, path in (("CTA endcard", CTA_PATH), ("voiceover", VOICEOVER_PATH), ("logo", LOGO_PATH)):
        if not path.exists():
            missing_assets.append(label)
    if missing_assets:
        issues.append(_recovery_issue(
            "Assets", "Attention Required", "warning",
            "One or more required media assets are missing.",
            "Missing: " + ", ".join(missing_assets) + ".",
            "Open the assets folder and restore the missing files.",
            "open_assets_folder",
        ))
    else:
        issues.append(_recovery_issue(
            "Assets", "Healthy", "ok",
            "Required media assets are present.",
            "Logo, CTA endcard, and voiceover files were found."
        ))

    # Caption Generator / Ollama
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(r.read())
        installed = {m.get("name", "") for m in data.get("models", [])}
        needed = {get_ai_model("identify"), get_ai_model("caption"), get_ai_model("verify")}
        missing = sorted(m for m in needed if m not in installed)
        if missing:
            issues.append(_recovery_issue(
                "Caption Generator", "Attention Required", "warning",
                "One or more local AI models are missing.",
                "Missing model(s): " + ", ".join(missing) + ".",
                "Open URL Import and use the Ollama install/model setup option.",
                "open_url_import",
            ))
        else:
            issues.append(_recovery_issue(
                "Caption Generator", "Healthy", "ok",
                "Local caption models are available.",
                "Ollama is running and the selected AI speed mode models are installed."
            ))
    except Exception:
        issues.append(_recovery_issue(
            "Caption Generator", "Attention Required", "warning",
            "Local AI is not reachable.",
            "Ollama may not be running, so automatic captions may not generate.",
            "Open URL Import and use the Ollama setup option.",
            "open_url_import",
        ))

    # Internet Archive
    if s.get("ia_access_key", "").strip() and s.get("ia_secret_key", "").strip():
        issues.append(_recovery_issue(
            "Internet Archive", "Configured", "ok",
            "Internet Archive credentials are saved.",
            "Uploads can use the saved local settings."
        ))
    else:
        issues.append(_recovery_issue(
            "Internet Archive", "Attention Required", "warning",
            "Internet Archive credentials are not configured.",
            "The app needs these credentials to host videos before scheduling.",
            "Open Settings and add your Internet Archive credentials.",
            "open_settings",
        ))

    # Buffer
    if s.get("buffer_key", "").strip() and s.get("buffer_channel_id", "").strip():
        issues.append(_recovery_issue(
            "Buffer", "Configured", "ok",
            "Buffer scheduling settings are present.",
            "The app has a saved API key and Instagram channel ID."
        ))
    else:
        issues.append(_recovery_issue(
            "Buffer", "Attention Required", "warning",
            "Buffer scheduling is not fully configured.",
            "The app needs a Buffer API key and Instagram channel ID to schedule posts.",
            "Open Settings and add your Buffer details.",
            "open_settings",
        ))

    # Storage
    missing_dirs = [p for p in (ASSETS_DIR, OUTPUT_DIR) if not p.exists()]
    free = shutil.disk_usage(Path(__file__).parent).free
    if missing_dirs:
        issues.append(_recovery_issue(
            "Storage", "Attention Required", "warning",
            "One or more application folders are missing.",
            "Missing folder(s): " + ", ".join(p.name for p in missing_dirs) + ".",
            "Create the missing folders.",
            "create_missing_folders",
        ))
    elif free < 2 * 1024 * 1024 * 1024:
        issues.append(_recovery_issue(
            "Storage", "Attention Required", "warning",
            "Available disk space is low.",
            "Video exports can fail when there is not enough free storage.",
            "Free up disk space before exporting more reels.",
            "",
        ))
    else:
        issues.append(_recovery_issue(
            "Storage", "Healthy", "ok",
            "Local storage looks healthy.",
            "Required folders exist and there is enough free disk space."
        ))

    return issues


def recovery_plain_message(error_text: str) -> str:
    text = (error_text or "").lower()
    if "403" in text or "forbidden" in text:
        return "A website refused access to the app. This usually means the page blocks automated requests or requires a browser login."
    if "401" in text or "unauthorized" in text or "authentication" in text:
        return "A saved login or API key appears to be invalid. Please review your credentials in Settings."
    if "429" in text or "rate" in text:
        return "A service is temporarily limiting requests. Waiting a few minutes and trying again is usually safest."
    if "timed out" in text or "timeout" in text:
        return "A request took too long to finish. Your connection or the remote service may be slow right now."
    if "ssl" in text or "certificate" in text:
        return "A secure connection could not be completed. This is usually a website or certificate issue."
    if "yt-dlp" in text:
        return "The video downloader could not complete the import. The reel may be private, unavailable, or require a fresh browser login."
    if "ffmpeg" in text or "video processing" in text:
        return "Video processing could not finish. The downloaded file may use a format the app could not prepare safely."
    if "buffer" in text:
        return "Buffer scheduling could not complete. Please review your Buffer connection and channel settings."
    if "archive" in text:
        return "The video upload service could not complete the upload. Please review your Internet Archive credentials or try again later."
    return "Something unexpected happened. The Recovery Assistant can scan the app and suggest safe next steps."
