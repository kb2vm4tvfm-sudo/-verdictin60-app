import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms-playwright")
)

import tkinter as tk
from tkinter import filedialog, ttk
import subprocess
import threading
import shutil
import math
import re
import json
import datetime
import time
from pathlib import Path
import case_library
from verdictin60_core.settings import load_settings, save_settings
from verdictin60_core.paths import name_to_filename, filename_to_display
from verdictin60_core.scheduling import next_post_datetime, batch_post_datetime, _date_at_post_time
from verdictin60_core.captions import caption_needs_fallback
from verdictin60_core.imports import (
    ytdlp_cmd, parse_docx_queue, download_video_url, parse_ytdlp_metadata,
)
from verdictin60_core.export import ExportError, run_export_pipeline
from verdictin60_core.ai import (
    AI_SPEED_MODES, get_ai_speed_mode, get_ai_model, get_ai_timeout,
    is_timeout_error, check_ollama, check_ollama_model_installed,
    _ollama_call, ollama_generate, ollama_identify,
)

ASSETS_DIR    = Path(__file__).parent / "assets"
OUTPUT_DIR    = Path(__file__).parent / "finished-reels"
CTA_PATH      = ASSETS_DIR / "cta-endcard.mp4"
VOICEOVER_PATH= ASSETS_DIR / "voiceover.mp3"
LOGO_PATH     = ASSETS_DIR / "logo.png"
TEMP_CTA      = Path(__file__).parent / "cta-with-voice.mp4"
LOG_PATH      = Path(__file__).parent / "export-log.txt"
RECOVERY_HISTORY_PATH = Path(__file__).parent / "recovery-history.json"
SOURCE_CACHE_PATH = Path(__file__).parent / "source-cache.json"
IMPORT_DOCX_PATH = Path(__file__).parent / "VerdictIn60_Import_With_Captions.docx"

BG          = "#000000"
CRIMSON     = "#940906"
CRIMSON_HOT = "#6b0604"
ERROR_RED   = "#ff4444"
WHITE       = "#FFFFFF"
OFF_WHITE   = "#e8e8e8"
MUTED       = "#555555"
LIGHT_GRAY  = "#888888"
DARK_CARD   = "#0e0e0e"
ROW_BG      = "#0d0d0d"
ROW_ALT     = "#111111"

FFMPEG      = shutil.which("ffmpeg")  or "/opt/homebrew/bin/ffmpeg"
FFPROBE     = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
DEFAULT_HASHTAGS = "#truecrime #verdictin60 #truecrimecommunity #coldcase #crimejunkie #justice #realcrimecases #crimeawareness #crimearchive #truecrimestories #crimeanalysis #lawandcrime #casefile #truecrimeobsessed #victimsmatter #crimebreakdown #truecrimefacts #truestoryreels #crimecommunity #crimehistory"

# ── Settings ──────────────────────────────────────────────────────────────────
# load_settings/save_settings moved to verdictin60_core.settings (Phase 1 refactor).
# ytdlp_cmd/parse_docx_queue/download_video_url moved to verdictin60_core.imports
# (Phase 2 refactor).
# AI_SPEED_MODES and the Ollama/AI helpers below moved to verdictin60_core.ai
# (Phase 4 refactor).


# ── Rule-Based Recovery Assistant ─────────────────────────────────────────────

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


# ── Instagram / Meta API ──────────────────────────────────────────────────────

def instagram_connect(app_id: str, app_secret: str, short_token: str) -> dict:
    """Exchange short-lived token → long-lived token → Page ID → IG Business ID.
    Returns a dict with keys: long_token, instagram_business_id, log, error (if any)."""
    import requests
    log = []

    # 1. Exchange for long-lived token (60 days)
    r = requests.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
        "grant_type":        "fb_exchange_token",
        "client_id":         app_id,
        "client_secret":     app_secret,
        "fb_exchange_token": short_token,
    }, timeout=15)
    data = r.json()
    log.append(f"[1] Token exchange → {r.status_code}: {json.dumps(data)[:300]}")
    if "error" in data:
        return {"error": f"Token exchange failed: {data['error'].get('message', data['error'])}", "log": log}
    long_token = data.get("access_token", "")
    if not long_token:
        return {"error": "Token exchange returned no access_token", "log": log}

    # 2a. Confirm token identity
    r_me = requests.get("https://graph.facebook.com/v19.0/me", params={
        "fields": "id,name", "access_token": long_token,
    }, timeout=15)
    me = r_me.json()
    log.append(f"[2a] /me → {r_me.status_code}: {json.dumps(me)[:300]}")

    # 2b. Try /me/accounts with full fields
    r2 = requests.get("https://graph.facebook.com/v19.0/me/accounts", params={
        "fields": "id,name,instagram_business_account",
        "access_token": long_token,
    }, timeout=15)
    accounts_data = r2.json()
    log.append(f"[2b] /me/accounts → {r2.status_code}: {json.dumps(accounts_data)[:400]}")
    pages = accounts_data.get("data", [])

    # 2c. If empty, try with limit=100
    if not pages:
        r2b = requests.get("https://graph.facebook.com/v19.0/me/accounts", params={
            "fields": "id,name,instagram_business_account",
            "limit": 100,
            "access_token": long_token,
        }, timeout=15)
        accounts_data2 = r2b.json()
        log.append(f"[2c] /me/accounts?limit=100 → {r2b.status_code}: {json.dumps(accounts_data2)[:400]}")
        pages = accounts_data2.get("data", [])

    if not pages:
        return {
            "error": (
                "No Facebook Pages found. Make sure your Instagram is connected to a "
                "Facebook Page and the token has pages_show_list permission."
            ),
            "long_token": long_token,
            "log": log,
        }

    # Find first page that has an IG business account
    ig_id = ""
    for page in pages:
        ig_id = page.get("instagram_business_account", {}).get("id", "")
        if ig_id:
            log.append(f"[3] Found IG Business Account: {ig_id} on page {page.get('name','?')}")
            break

    if not ig_id:
        # Try fetching instagram_business_account explicitly for each page
        for page in pages:
            pid = page["id"]
            r3 = requests.get(f"https://graph.facebook.com/v19.0/{pid}", params={
                "fields": "instagram_business_account",
                "access_token": long_token,
            }, timeout=15)
            ig_data = r3.json()
            log.append(f"[3] Page {pid} explicit fetch → {json.dumps(ig_data)[:200]}")
            ig_id = ig_data.get("instagram_business_account", {}).get("id", "")
            if ig_id:
                break

    if not ig_id:
        return {
            "error": "No Instagram Business Account linked to any Facebook Page.",
            "long_token": long_token,
            "log": log,
        }

    return {"long_token": long_token, "instagram_business_id": ig_id, "log": log}


def autodetect_instagram_id(long_token: str) -> dict:
    """Try every known approach to find the Instagram Business Account ID.
    Returns: {instagram_business_id, log, error}"""
    import requests
    log = []

    def get(url, params):
        params["access_token"] = long_token
        r = requests.get(url, params=params, timeout=15)
        body = r.json()
        log.append(f"GET {url.replace('https://graph.facebook.com/v19.0','')}"
                   f"?{','.join(k+'='+str(v) for k,v in params.items() if k!='access_token')}"
                   f" → {r.status_code}: {json.dumps(body)[:500]}")
        return body

    def find_ig_in_pages(pages):
        for page in pages:
            ig = page.get("instagram_business_account", {})
            if isinstance(ig, dict) and ig.get("id"):
                return ig["id"], page.get("name", "?")
        return None, None

    BASE = "https://graph.facebook.com/v19.0"

    # Approach 1: /me/accounts with instagram_business_account field
    data1 = get(f"{BASE}/me/accounts", {"fields": "id,name,instagram_business_account", "limit": 100})
    pages1 = data1.get("data", [])
    ig_id, page_name = find_ig_in_pages(pages1)
    if ig_id:
        return {"instagram_business_id": ig_id, "log": log,
                "note": f"Found via /me/accounts on page '{page_name}'"}

    # Approach 2: nested accounts field on /me
    data2 = get(f"{BASE}/me", {"fields": "id,name,accounts{id,name,instagram_business_account}"})
    pages2 = data2.get("accounts", {}).get("data", [])
    ig_id, page_name = find_ig_in_pages(pages2)
    if ig_id:
        return {"instagram_business_id": ig_id, "log": log,
                "note": f"Found via /me?fields=accounts on page '{page_name}'"}

    # Approach 3: for each page from approach 1, fetch instagram_business_account explicitly
    all_pages = pages1 or pages2
    if all_pages:
        for page in all_pages:
            pid = page.get("id")
            if not pid:
                continue
            data3 = get(f"{BASE}/{pid}", {"fields": "id,name,instagram_business_account"})
            ig_id = data3.get("instagram_business_account", {}).get("id", "")
            if ig_id:
                return {"instagram_business_id": ig_id, "log": log,
                        "note": f"Found via explicit page fetch for page {pid}"}
    else:
        log.append("No pages found in any /me/accounts response — token may lack pages_show_list permission")

    # Approach 4: try /me/subscribed_apps (shows what pages token has access to)
    data4 = get(f"{BASE}/me/subscribed_apps", {})
    log.append(f"subscribed_apps data (diagnostic only): {json.dumps(data4)[:300]}")

    return {
        "error": (
            "Could not find an Instagram Business Account automatically.\n\n"
            "To find it manually:\n"
            "• Go to business.facebook.com → Settings → Instagram Accounts\n"
            "• Click your account → copy the ID from the URL\n"
            "  (or Settings → Account → Business Account Info)\n\n"
            "Then paste the numeric ID into the field above."
        ),
        "log": log,
    }


def fetch_ig_media_metrics(ig_business_id: str, long_token: str,
                           case_name: str, scheduled_date: str) -> dict | None:
    """Find the Instagram media post matching case_name/date and return its metrics."""
    import requests

    # Fetch recent media (up to 50)
    r = requests.get(f"https://graph.facebook.com/v19.0/{ig_business_id}/media", params={
        "fields":       "id,caption,timestamp,media_type",
        "limit":        50,
        "access_token": long_token,
    }, timeout=15)
    media_list = r.json().get("data", [])
    if not media_list:
        return None

    # Match by scheduled_date (post timestamp) or caption containing case name
    target_date = scheduled_date[:10] if scheduled_date else ""
    matched_id = None
    for item in media_list:
        ts = item.get("timestamp", "")[:10]
        caption = item.get("caption", "").lower()
        name_lower = case_name.lower()
        if ts == target_date or name_lower in caption:
            matched_id = item["id"]
            break

    if not matched_id:
        return None

    # Fetch insights for that media
    r2 = requests.get(f"https://graph.facebook.com/v19.0/{matched_id}/insights", params={
        "metric":       "video_views,likes,comments,reach",
        "access_token": long_token,
    }, timeout=15)
    insights = r2.json().get("data", [])
    metrics = {}
    for item in insights:
        metrics[item["name"]] = item.get("values", [{}])[-1].get("value", 0)

    # Also try direct fields for likes/comments (more reliable)
    r3 = requests.get(f"https://graph.facebook.com/v19.0/{matched_id}", params={
        "fields":       "like_count,comments_count",
        "access_token": long_token,
    }, timeout=15)
    direct = r3.json()
    return {
        "views":    metrics.get("video_views", "—"),
        "likes":    direct.get("like_count",    metrics.get("likes", "—")),
        "comments": direct.get("comments_count", metrics.get("comments", "—")),
        "reach":    metrics.get("reach", "—"),
        "media_id": matched_id,
    }


# ── Name cleaning ─────────────────────────────────────────────────────────────

# name_to_filename/filename_to_display moved to verdictin60_core.paths (Phase 1 refactor).


# ── Scheduling helpers ────────────────────────────────────────────────────────
# next_post_datetime/batch_post_datetime/_date_at_post_time moved to
# verdictin60_core.scheduling (Phase 1 refactor).


def _resolve_buffer_org_id(buffer_key: str, channel_id: str) -> str:
    """Fetch and cache the Buffer organizationId for channel_id."""
    s = load_settings()
    cached = (s.get("buffer_organization_id") or "").strip()
    if cached:
        return cached
    try:
        import requests as _rq
        r = _rq.post(
            "https://api.buffer.com/graphql",
            json={"query": '{ channel(input: { id: "%s" }) { organizationId } }' % channel_id},
            headers={"Authorization": f"Bearer {buffer_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        org_id = (r.json().get("data", {}).get("channel") or {}).get("organizationId", "")
        if org_id:
            s["buffer_organization_id"] = org_id
            save_settings(s)
        return org_id
    except Exception as e:
        print(f"[{_ts()} BUFFER] _resolve_buffer_org_id failed: {e}")
        return ""


def fetch_buffer_scheduled_texts(buffer_key: str, channel_id: str) -> tuple[list[str], str]:
    """Return (list of scheduled post texts, error_message)."""
    try:
        import requests as _rq
        org_id = _resolve_buffer_org_id(buffer_key, channel_id)
        if not org_id:
            return [], "Could not resolve Buffer organizationId for this channel."
        query = (
            '{ posts(input: { organizationId: "%s",'
            '  filter: { channelIds: ["%s"], status: [scheduled] } }, first: 100) {'
            '  edges { node { text } }'
            '} }' % (org_id, channel_id)
        )
        r = _rq.post(
            "https://api.buffer.com/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {buffer_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        gql_errors = data.get("errors")
        if gql_errors:
            return [], f"Buffer API error: {gql_errors[0].get('message', gql_errors)}"
        edges = data.get("data", {}).get("posts", {}).get("edges", [])
        texts = [e["node"]["text"] for e in edges if e.get("node", {}).get("text")]
        print(f"[{_ts()} BUFFER] fetch_buffer_scheduled_texts: {len(texts)} posts")
        return texts, ""
    except Exception as e:
        print(f"[{_ts()} BUFFER] fetch_buffer_scheduled_texts failed: {e}")
        return [], str(e)


def get_next_available_date(buffer_key, channel_id, post_time, offset_days=0):
    import pytz

    # Try to query Buffer API for the latest scheduled post's dueAt
    last_due_str = ""
    if buffer_key and channel_id:
        try:
            import requests as _rq
            query = """
{ posts(input: { status: scheduled, channelIds: ["%s"], limit: 50 }) {
    edges { node { id dueAt } }
} }""" % channel_id
            r = _rq.post(
                "https://api.buffer.com/graphql",
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {buffer_key}",
                    "Content-Type": "application/json",
                },
                timeout=8,
            )
            edges = r.json().get("data", {}).get("posts", {}).get("edges", [])
            if edges:
                dues = [e["node"]["dueAt"] for e in edges if e.get("node", {}).get("dueAt")]
                if dues:
                    last_due_str = max(dues)
                    print(f"[{_ts()} BUFFER] Latest scheduled post dueAt from API: {last_due_str}")
        except Exception as e:
            print(f"[{_ts()} BUFFER] Buffer API query failed, using settings fallback: {e}")

    # Fall back to settings.json if API didn't return a date
    if not last_due_str:
        settings = load_settings()
        last_due_str = settings.get("last_scheduled_date", "")
        print(f"[{_ts()} BUFFER] Using last_scheduled_date from settings: {last_due_str!r}")

    if last_due_str:
        try:
            last_date = datetime.datetime.fromisoformat(last_due_str.replace("Z", "+00:00"))
            candidate = last_date.date()
            base = candidate if candidate >= datetime.date.today() else datetime.date.today()
        except Exception:
            base = datetime.date.today()
    else:
        base = datetime.date.today()

    print(f"[{_ts()} BUFFER] base={base}, offset_days={offset_days}")
    next_date = base + datetime.timedelta(days=1 + offset_days)
    h, m = map(int, post_time.split(":"))
    local_tz = datetime.datetime.now().astimezone().tzinfo
    dt = datetime.datetime(next_date.year, next_date.month, next_date.day, h, m, tzinfo=local_tz)
    utc_dt = dt.astimezone(pytz.utc)
    print(f"[{_ts()} BUFFER] Next slot: {utc_dt}")
    return utc_dt


def next_available_date_safe(buffer_key: str, channel_id: str, post_time: str,
                             offset_days: int = 0, limit_s: float = 10.0) -> datetime.datetime:
    """get_next_available_date with a hard wall-clock cap. If the Buffer query
    hasn't returned within limit_s seconds (e.g. DNS/TLS stall that the requests
    timeout doesn't bound), fall back to tomorrow + offset_days immediately so
    the export never blocks."""
    fallback = batch_post_datetime(post_time, offset_days)
    box = {"result": fallback}

    def worker():
        try:
            box["result"] = get_next_available_date(
                buffer_key, channel_id, post_time, offset_days
            )
        except Exception:
            box["result"] = fallback

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(limit_s)
    # If still running, abandon it (daemon) and use the fallback already in box.
    return box["result"]


# ── Background drawing ────────────────────────────────────────────────────────

def _draw_watermarks(canvas, w, h):
    c = "#1a1a1a"
    for x1, y1, x2, y2 in [(28, 60, 68, 100), (20, 50, 30, 60), (66, 98, 76, 108)]:
        canvas.create_rectangle(x1, y1, x2, y2, fill=c, outline="")
    canvas.create_rectangle(20, 95, 80, 102, fill=c, outline="")
    cx, cy, r = w - 55, h - 65, 22
    canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=c, width=5)
    canvas.create_line(cx+int(r*.7), cy+int(r*.7), cx+int(r*1.7), cy+int(r*1.7), fill=c, width=5)
    bx, by = w - 55, 75
    for i in range(5):
        rr = 10 + i * 8
        canvas.create_arc(bx-rr, by-rr//2, bx+rr, by+rr//2,
                          start=200, extent=140, style="arc", outline=c, width=2)
    pts, bx2, by2, br = [], 55, h - 65, 28
    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        pts += [bx2 + br * math.cos(rad), by2 + br * math.sin(rad)]
    canvas.create_polygon(pts, outline=c, fill="", width=2)
    canvas.create_oval(bx2-15, by2-15, bx2+15, by2+15, outline=c, width=2)


def _draw_grain(canvas, w, h):
    for gy in range(0, h, 18):
        for gx in range(0, w, 18):
            shade = "#0d0d0d" if (gx // 18 + gy // 18) % 2 == 0 else "#0a0a0a"
            canvas.create_rectangle(gx, gy, gx+1, gy+1, fill=shade, outline="")


def _bind_hover(widget, normal_bg, hover_bg, normal_fg=None, hover_fg=None):
    def on_enter(_):
        if getattr(widget, "_lbtn_disabled", False):
            return
        widget.config(bg=hover_bg)
        if hover_fg:
            widget.config(fg=hover_fg)
    def on_leave(_):
        if getattr(widget, "_lbtn_disabled", False):
            return
        widget.config(bg=normal_bg)
        if normal_fg:
            widget.config(fg=normal_fg)
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


def _make_lbtn(parent, text, command, bg, fg=WHITE, font=("Helvetica", 12, "bold"),
               hover_bg=None, hover_fg=None, pady=14, padx=20, anchor="center",
               normal_fg=None):
    """tk.Label styled as a button — respects bg on macOS unlike tk.Button."""
    if hover_bg is None:
        hover_bg = bg
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                   cursor="hand2", pady=pady, padx=padx, anchor=anchor,
                   highlightthickness=0)
    lbl._lbtn_disabled = False
    lbl._lbtn_normal_bg = bg
    lbl._lbtn_hover_bg  = hover_bg
    lbl._lbtn_normal_fg = normal_fg or fg
    lbl._lbtn_hover_fg  = hover_fg or fg
    lbl._lbtn_command   = command

    def _click(e):
        if not lbl._lbtn_disabled:
            command()
    def _enter(e):
        if not lbl._lbtn_disabled:
            lbl.config(bg=hover_bg, fg=lbl._lbtn_hover_fg)
    def _leave(e):
        if not lbl._lbtn_disabled:
            lbl.config(bg=bg, fg=lbl._lbtn_normal_fg)

    lbl.bind("<Button-1>", _click)
    lbl.bind("<Enter>", _enter)
    lbl.bind("<Leave>", _leave)
    return lbl


def _lbtn_enable(lbl, bg, fg=WHITE, hover_bg=None):
    lbl._lbtn_disabled = False
    lbl._lbtn_normal_bg = bg
    lbl._lbtn_hover_bg = hover_bg or bg
    lbl._lbtn_normal_fg = fg
    lbl.config(bg=bg, fg=fg)


def _lbtn_disable(lbl, bg, fg="#888888"):
    lbl._lbtn_disabled = True
    lbl.config(bg=bg, fg=fg)


def reformat_caption(case_title: str, raw_caption: str) -> str:
    import re as _re
    text = raw_caption.strip()
    text = _re.sub(r'follow @\S+.*', '', text, flags=_re.IGNORECASE).strip()
    text = _re.sub(r'#\w+(\s+#\w+)*\s*$', '', text, flags=_re.MULTILINE).strip()
    sentences = _re.split(r'(?<=[.!?])\s+', text)
    paragraphs = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and len(sentences[i]) < 80:
            paragraphs.append(sentences[i] + ' ' + sentences[i+1])
            i += 2
        else:
            paragraphs.append(sentences[i])
            i += 1
    body = '\n\n'.join(paragraphs)
    return f"{body}\n\nFollow @verdictin60 for daily true crime 🩸🔪\n\n{DEFAULT_HASHTAGS}"


def creator_credit_line(uploader: str) -> str:
    """Return a subtle credit line for the original reel creator."""
    handle = (uploader or "").strip()
    handle = re.sub(r"^https?://(?:www\.)?instagram\.com/", "", handle, flags=re.I)
    handle = handle.strip("/ @")
    handle = re.sub(r"[^A-Za-z0-9_.]", "", handle)
    if not handle or handle.lower() in {"instagram", "unknown", "video"}:
        return ""
    return f"Original video via @{handle}."


def ensure_creator_credit(caption: str, uploader: str) -> str:
    """Insert creator credit before CTA/hashtags without changing the main story."""
    text = (caption or "").strip()
    credit = creator_credit_line(uploader)
    if not text or not credit:
        return text
    if re.search(r"\bOriginal video via @", text, re.I):
        return text

    hashtag_block = ""
    hashtag_match = re.search(r"(\n\s*(?:#[\w]+\s*){5,})\s*$", text, re.S)
    if hashtag_match:
        hashtag_block = hashtag_match.group(1).strip()
        text = text[:hashtag_match.start()].rstrip()

    cta_match = re.search(r"(\n\s*Follow @VerdictIn60[^\n]*\.?)\s*$", text, re.I)
    if cta_match:
        cta = cta_match.group(1).strip()
        text = text[:cta_match.start()].rstrip()
        text = f"{text}\n\n{credit}\n\n{cta}".strip()
    else:
        text = f"{text}\n\n{credit}".strip()

    if hashtag_block:
        text = f"{text}\n\n{hashtag_block}"
    return text


def fallback_verdict_caption(case_title: str, source_caption: str,
                             research_section: str = "", cautious: bool = False) -> str:
    """Build a usable review caption when AI generation fails or times out."""
    import re as _re
    weak_verification = cautious or any(
        marker in (research_section or "")
        for marker in (
            "No independent source was found",
            "No accessible reputable reporting source found",
            "Additional reputable reporting review recommended",
            "No independent sources were located",
            "Encyclopedia reference used for orientation only",
            "Encyclopedia material used for orientation only",
        )
    )
    source = source_caption.strip()
    source = _re.sub(r'\[?#([A-Za-z0-9_]+)\]?\([^)]+\)', r'#\1', source)
    source = _re.sub(r'https?://\S+', '', source)
    source = _re.sub(r'#\w+', '', source).strip()
    source = _re.sub(r'\s+', ' ', source)

    sentences = [
        s.strip()
        for s in _re.split(r'(?<=[.!?])\s+', source)
        if len(s.strip()) > 20
    ]
    if not sentences:
        sentences = [f"{case_title} is the focus of this case."]

    subject = case_title or "This case"
    hook = f"VerdictIn60: {subject}"

    if weak_verification:
        body = "\n\n".join([
            hook,
            (
                f"{subject} is the focus of a story that continues to draw public "
                "attention because of the questions surrounding the timeline, "
                "search effort, and aftermath."
            ),
            (
                "With limited accessible source material, the most responsible way "
                "to cover it is to separate confirmed facts from online speculation "
                "and avoid repeating details that cannot be independently checked."
            ),
            (
                "Cases like this show why viral stories need careful sourcing: the "
                "details that spread fastest are not always the details that are "
                "best supported."
            ),
            "What detail do you think should be verified first before people share the story?",
        ])
        research = research_section or source_section_for_caption([])
        return (
            f"{body}\n\n"
            f"{research}\n\n"
            "Follow @VerdictIn60 for daily true crime.\n\n"
            f"{DEFAULT_HASHTAGS}"
        )

    selected = sentences[:6]

    opener = selected[0]
    if subject.lower() not in opener.lower():
        opener = f"{subject} is the focus of this case. {opener}"

    body_parts = [
        hook,
        opener,
    ]
    if len(selected) > 1:
        body_parts.extend(selected[1:5])
    body_parts.append(
        "This case is a reminder that accountability, memory, and historical truth "
        "can remain urgent long after the original crimes."
    )

    body = "\n\n".join(body_parts)
    research = research_section or source_section_for_caption([])
    return (
        f"{body}\n\n"
        f"{research}\n\n"
        "Follow @VerdictIn60 for daily true crime.\n\n"
        f"{DEFAULT_HASHTAGS}"
    )


# caption_needs_fallback moved to verdictin60_core.captions (Phase 1 refactor).


# ── Upload & Buffer ───────────────────────────────────────────────────────────

def upload_video(video_path: Path) -> str:
    import os
    s = load_settings()
    ia_access = s.get("ia_access_key", "").strip()
    ia_secret = s.get("ia_secret_key", "").strip()

    print(f"[UPLOAD] ia_access exists: {bool(ia_access)}, ia_secret exists: {bool(ia_secret)}")

    if not ia_access or not ia_secret:
        raise Exception(
            "Upload failed: Internet Archive not configured. "
            "Open Settings and add your IA Access Key and Secret Key."
        )

    video_path_str = str(video_path)
    filename       = os.path.basename(video_path_str)
    identifier     = f"verdictin60-{filename.replace('.mp4', '').lower().replace(' ', '-')}"
    upload_url     = f"https://s3.us.archive.org/{identifier}/{filename}"
    public_url     = f"https://archive.org/download/{identifier}/{filename}"

    cmd = [
        "curl", "-s", "-X", "PUT", upload_url,
        "-H", f"authorization: LOW {ia_access}:{ia_secret}",
        "-H", "x-archive-auto-make-bucket:1",
        "-H", "x-archive-meta-mediatype:movies",
        "-H", "x-archive-meta-subject:truecrime",
        "-H", "Content-Type: video/mp4",
        "--data-binary", f"@{video_path_str}",
        "--max-time", "600",
    ]
    print(f"[UPLOAD] CMD: {' '.join(cmd[:6])}...")
    print(f"[UPLOAD] file: {video_path_str}  exists: {os.path.exists(video_path_str)}")
    print(f"[UPLOAD] upload_url: {upload_url}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=310)

    print(f"[UPLOAD] returncode: {result.returncode}")
    print(f"[UPLOAD] stdout: {result.stdout[:300]}")
    print(f"[UPLOAD] stderr: {result.stderr[:300]}")

    if result.returncode != 0:
        raise Exception(f"Upload failed: {result.stderr[:200]}")

    # Return the public URL immediately — Archive.org may need extra time before
    # Buffer can read it, so callers should poll/retry before scheduling.
    print(f"[{_ts()} UPLOAD] Upload complete. Returning URL immediately (no polling).")
    return public_url


def schedule_to_buffer(caption: str, video_url: str, channel_id: str,
                       buffer_key: str, post_time: str,
                       due_at_dt: datetime.datetime = None) -> tuple:
    import requests
    if due_at_dt is None:
        due_at = next_post_datetime(post_time)
    else:
        due_at = due_at_dt
    due_str = due_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Use GraphQL variables for text/channelId/dueAt so apostrophes, em dashes,
    # emoji and any other characters in the caption are handled safely without
    # manual escaping. Only video_url is interpolated (a clean archive.org URL).
    mutation = """
mutation CreatePost($text: String!, $channelId: ChannelId!, $dueAt: DateTime) {
  createPost(
    input: {
      text: $text
      channelId: $channelId
      schedulingType: automatic
      mode: customScheduled
      dueAt: $dueAt
      metadata: {
        instagram: {
          type: reel
          shouldShareToFeed: true
        }
      }
      assets: [{ video: { url: "%s" } }]
    }
  ) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}
""" % video_url

    variables = {
        "text": caption,
        "channelId": channel_id,
        "dueAt": due_str,
    }

    r = requests.post(
        "https://api.buffer.com/graphql",
        json={"query": mutation, "variables": variables},
        headers={
            "Authorization": f"Bearer {buffer_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    return r.text, r.json()


def buffer_video_not_ready(message: str) -> bool:
    msg = (message or "").lower()
    return (
        "404" in msg
        or "503" in msg
        or "not accessible" in msg
        or "service unavailable" in msg
        or "verify the url points to a public" in msg
    )


def public_url_http_code(url: str, timeout_s: int = 20) -> str:
    try:
        check = subprocess.run(
            [
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "-L", "--max-time", str(timeout_s), url,
            ],
            capture_output=True, text=True, timeout=timeout_s + 5,
        )
        return check.stdout.strip() or "000"
    except Exception:
        return "000"


def wait_for_public_video_url(url: str, status_cb=None, log_lines=None,
                              max_attempts: int = 8) -> bool:
    """Wait until Archive.org exposes the uploaded file as an HTTP 200 URL."""
    waits = [0, 15, 30, 45, 60, 75, 90, 120]
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            wait_s = waits[min(attempt - 1, len(waits) - 1)]
            if status_cb:
                status_cb(
                    f"⏳  Archive.org still processing — waiting {wait_s}s "
                    f"({attempt}/{max_attempts})"
                )
            time.sleep(wait_s)
        code = public_url_http_code(url)
        if log_lines is not None:
            log_lines.append(f"Archive.org public URL check {attempt}/{max_attempts}: HTTP {code}")
        if code == "200":
            return True
    return False


class UploadPendingError(Exception):
    """Raised when Archive.org upload succeeded but file is not yet HTTP-200 after all polls."""
    def __init__(self, public_url: str):
        self.public_url = public_url
        super().__init__(f"Archive.org is still processing: {public_url}")


# ── Dialogs ───────────────────────────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, True)

        s = load_settings()

        # Top accent bar
        tk.Frame(self, bg=CRIMSON, height=3).pack(fill="x")

        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=30, pady=(24, 0))
        tk.Label(hdr, text="SETTINGS", font=("Helvetica", 14, "bold"),
                 fg=WHITE, bg=BG, anchor="w").pack(side="left")

        fields_frame = tk.Frame(self, bg=BG)
        fields_frame.pack(padx=30, fill="x", pady=(8, 0))

        self._vars = {}

        # ── Buffer section ────────────────────────────────────────────────────
        tk.Frame(fields_frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(12, 8))
        tk.Label(fields_frame, text="BUFFER", font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        buffer_rows = [
            ("buffer_key",        "Buffer API Key",              s.get("buffer_key", ""),        True),
            ("buffer_channel_id", "Buffer Instagram Channel ID", s.get("buffer_channel_id", ""), False),
            ("post_time",         "Daily Post Time (HH:MM)",     s.get("post_time", "18:00"),    False),
        ]
        for key, label, value, masked in buffer_rows:
            self._make_field(fields_frame, key, label, value, masked)

        # ── Internet Archive section ──────────────────────────────────────────
        tk.Frame(fields_frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(20, 8))
        tk.Label(fields_frame, text="INTERNET ARCHIVE  —  VIDEO HOSTING", font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        ia_rows = [
            ("ia_access_key", "IA Access Key",  s.get("ia_access_key", ""),  False),
            ("ia_secret_key", "IA Secret Key",  s.get("ia_secret_key", ""),  True),
        ]
        for key, label, value, masked in ia_rows:
            self._make_field(fields_frame, key, label, value, masked)

        # ── AI section ────────────────────────────────────────────────────────
        tk.Frame(fields_frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(20, 8))
        tk.Label(fields_frame, text="AI  —  OLLAMA SETTINGS", font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        tk.Label(fields_frame, text="AI SPEED MODE", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        ai_speed_options = [
            "Fast",
            "Balanced",
            "Best Accuracy",
        ]
        current_speed = s.get("ai_speed_mode", "")
        if current_speed not in AI_SPEED_MODES:
            current_ai = s.get("ai_model", "qwen3:14b")
            current_speed = "Best Accuracy" if current_ai == "qwen3:32b" else "Balanced"
        self._ai_speed_var = tk.StringVar(value=current_speed or "Balanced")
        ai_dropdown = ttk.Combobox(
            fields_frame, textvariable=self._ai_speed_var,
            values=ai_speed_options, state="readonly",
            font=("Helvetica", 11)
        )
        ai_dropdown.pack(fill="x", ipady=4)

        tk.Label(fields_frame, text="PREFERRED BROWSER FOR COOKIES", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        browser_options = ["chrome", "safari", "firefox"]
        self._browser_var = tk.StringVar(value=s.get("preferred_browser", "chrome"))
        browser_dropdown = ttk.Combobox(
            fields_frame, textvariable=self._browser_var,
            values=browser_options, state="readonly",
            font=("Helvetica", 11)
        )
        browser_dropdown.pack(fill="x", ipady=4)

        # ── Save button ───────────────────────────────────────────────────────
        tk.Frame(self, bg="#2a2a2a", height=1).pack(fill="x", padx=30, pady=(20, 0))
        btn = _make_lbtn(
            self, "SAVE SETTINGS", self._save,
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 11, "bold"), pady=12, padx=20
        )
        btn.pack(padx=30, fill="x", pady=(12, 24))

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        dw, dh = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"{max(dw, 420)}x{dh}+{px+(pw-dw)//2}+{py+(ph-dh)//2}")

    def _make_field(self, parent, key, label, value, masked):
        tk.Label(parent, text=label.upper(), font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        e = tk.Entry(parent, show="*" if masked else "",
                     font=("Helvetica", 11), fg=WHITE, bg="#1a1a1a",
                     insertbackground=WHITE, relief="flat",
                     highlightthickness=1, highlightbackground="#2a2a2a",
                     highlightcolor=CRIMSON)
        e.insert(0, value)
        e.pack(fill="x", ipady=8)
        var = tk.StringVar(value=value)
        e.config(textvariable=var)
        self._vars[key] = var

    def _save(self):
        current = load_settings()
        current.update({k: v.get().strip() for k, v in self._vars.items()})
        speed_mode = self._ai_speed_var.get().strip()
        if speed_mode not in AI_SPEED_MODES:
            speed_mode = "Balanced"
        current["ai_speed_mode"] = speed_mode
        current["ai_model"] = AI_SPEED_MODES[speed_mode]["caption"]
        current["preferred_browser"] = self._browser_var.get().strip()
        save_settings(current)
        self.destroy()


# ── Timestamp helper ──────────────────────────────────────────────────────────
def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def fetch_wikipedia_summary(case_name: str):
    """Fetch Wikipedia article via curl (avoids macOS Python SSL cert issues).
    If the direct page summary is short (<500 chars), searches for a richer article.
    If the best summary is still under 1000 chars, fetches the full article extract.
    Returns (extract_text, page_title). Both are empty strings on failure."""
    import urllib.parse

    def _curl_json(url):
        r = subprocess.run(
            ["curl", "-s", "-A", "VerdictIn60/1.0", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout:
            try:
                return json.loads(r.stdout)
            except Exception:
                pass
        return {}

    def _full_extract(page_title: str) -> str:
        """Fetch full article plaintext via MediaWiki API."""
        enc = urllib.parse.quote(page_title.replace(" ", "_"))
        url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=query&titles={enc}&prop=extracts"
            "&exintro=false&explaintext=true&format=json"
        )
        data = _curl_json(url)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            text = page.get("extract", "")
            if text:
                return text
        return ""

    try:
        search_term = urllib.parse.quote(case_name.replace(" ", "_"))

        # Step 1: direct page lookup
        data    = _curl_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term}")
        extract = data.get("extract", "")
        title   = data.get("title", "")

        # Step 2: if result is thin, search for a better article — but only
        # upgrade if the new page title still refers to the same person/case.
        if len(extract) < 500:
            search_url = (
                "https://en.wikipedia.org/w/api.php"
                f"?action=query&list=search&srsearch={search_term}"
                "&format=json&srlimit=5"
            )
            search_data = _curl_json(search_url)
            hits = search_data.get("query", {}).get("search", [])
            case_words = set(case_name.lower().split())
            for hit in hits:
                candidate_title = hit["title"]
                candidate_words = set(candidate_title.lower().split())
                # Only upgrade if the candidate page title shares meaningful
                # words with the case name (avoids author/documentary redirects)
                if not case_words & candidate_words:
                    print(f"[{_ts()} URL_IMPORT] Wikipedia skipped unrelated: {candidate_title!r}")
                    continue
                page_term = urllib.parse.quote(candidate_title.replace(" ", "_"))
                page_data = _curl_json(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_term}"
                )
                page_extract = page_data.get("extract", "")
                if len(page_extract) > len(extract):
                    extract = page_extract
                    title   = page_data.get("title", title)
                    print(f"[{_ts()} URL_IMPORT] Wikipedia upgraded to: {title!r} ({len(extract)} chars)")
                    break

        # Step 3: if still under 1000 chars, fetch the full article extract
        if title and len(extract) < 1000:
            full = _full_extract(title)
            if len(full) > len(extract):
                extract = full
                print(f"[{_ts()} URL_IMPORT] Wikipedia full article fetched: {title!r} ({len(extract)} chars)")

        if extract:
            print(f"[{_ts()} URL_IMPORT] Wikipedia facts: {title!r} ({len(extract)} chars)")
            return extract, title
    except Exception as e:
        print(f"[{_ts()} URL_IMPORT] Wikipedia lookup failed: {e}")
    return "", ""


def _strip_html_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;|&apos;", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_readable_text(raw_html: str) -> str:
    """Extract article-like text from HTML, falling back to whole-page text."""
    candidates = []
    for pattern in (
        r"(?is)<article\b[^>]*>(.*?)</article>",
        r"(?is)<main\b[^>]*>(.*?)</main>",
        r'(?is)<div\b[^>]+(?:article|story|content|entry|post|body)[^>]*>(.*?)</div>',
    ):
        for m in re.finditer(pattern, raw_html):
            text = _strip_html_text(m.group(1))
            if len(text) > 500:
                candidates.append(text)
    if candidates:
        return max(candidates, key=len)
    return _strip_html_text(raw_html)


def _looks_like_block_page(text: str) -> bool:
    hay = text[:2500].lower()
    markers = (
        "enable javascript", "verify you are human", "checking your browser",
        "access denied", "403 forbidden", "are you a robot", "captcha",
        "cloudflare", "please disable your ad blocker", "subscribe to continue",
        "sign in to continue", "consent.google.com",
    )
    return any(m in hay for m in markers)


def _fetch_url_text(url: str, timeout: int = 10) -> str:
    raw = _fetch_raw_url(url, timeout=timeout)
    if not raw:
        return ""
    return _extract_readable_text(raw)[:5000]


def _page_title(raw_html: str) -> str:
    """Extract the <title> tag text from raw HTML, stripped of site name suffixes."""
    m = re.search(r'<title[^>]*>([^<]{3,200})</title>', raw_html, re.I)
    if not m:
        return ""
    title = re.sub(r'\s*[-|—]\s*(BBC|CNN|Reuters|AP News|NBC News|CBS News|ABC News|'
                   r'The New York Times|Washington Post|The Guardian|Britannica)[^\n]*$', '',
                   m.group(1), flags=re.I).strip()
    title = re.sub(r'&amp;', '&', title)
    title = re.sub(r'&#\d+;', '', title)
    return title[:100]


def _fetch_raw_url(url: str, timeout: int = 10) -> str:
    try:
        import ssl as _ssl
        import urllib.request
        _ctx = None
        try:
            import certifi as _certifi
            _ctx = _ssl.create_default_context(cafile=_certifi.where())
        except Exception as ssl_e:
            print(f"[{_ts()} SOURCES] certifi unavailable ({ssl_e}) — SSL unverified")
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36 VerdictIn60/1.0"
                )
            }
        )
        kw = {"context": _ctx} if _ctx else {}
        with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
            data = r.read(350_000)
            return data.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[{_ts()} SOURCES] fetch FAILED — {type(e).__name__}: {e} — url={url[:120]}")
        return ""


def _find_browser_executable() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("msedge"),
    ]
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    return ""


def _fetch_playwright_rendered_html(url: str, timeout: int = 24) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""

    try:
        with sync_playwright() as p:
            browser = None
            launch_errors = []
            launch_args = [
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-crash-reporter",
                "--disable-software-rasterizer",
            ]
            for launch_kwargs in (
                {"channel": "chrome", "headless": True, "args": launch_args},
                {"headless": True, "args": launch_args},
            ):
                try:
                    browser = p.chromium.launch(**launch_kwargs)
                    break
                except Exception as e:
                    launch_errors.append(str(e).splitlines()[0])
            if browser is None:
                print(
                    f"[{_ts()} SOURCES] Playwright browser unavailable: "
                    f"{'; '.join(launch_errors)[:220]}"
                )
                return ""
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                viewport={"width": 1365, "height": 900},
            )
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(2500)
            html = page.content()
            browser.close()
            if html and len(html) > 500:
                print(f"[{_ts()} SOURCES] Playwright reader loaded {len(html)} bytes: {url[:90]}")
                return html
    except Exception as e:
        print(f"[{_ts()} SOURCES] Playwright reader failed: {type(e).__name__}: {e}")
    return ""


def _fetch_browser_rendered_html(url: str, timeout: int = 24) -> str:
    """Render a public page with a real browser engine and return its DOM.

    This is a fallback for news sites that block urllib/requests but still load
    in a normal browser. It does not bypass paywalls or captchas.
    """
    html = _fetch_playwright_rendered_html(url, timeout=timeout)
    if html:
        return html

    browser = _find_browser_executable()
    if not browser:
        print(f"[{_ts()} SOURCES] browser reader unavailable: Chrome/Chromium not found")
        return ""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="verdictin60-browser-") as profile_dir:
        base_cmd = [
            browser,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-crash-reporter",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_dir}",
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "--virtual-time-budget=8000",
            "--dump-dom",
            url,
        ]
        for cmd in (base_cmd, [arg.replace("--headless=new", "--headless") for arg in base_cmd]):
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                html = r.stdout or ""
                if r.returncode == 0 and len(html) > 500:
                    print(f"[{_ts()} SOURCES] browser reader loaded {len(html)} bytes: {url[:90]}")
                    return html
                stderr = (r.stderr or "").strip().splitlines()
                detail = stderr[-1] if stderr else f"returncode={r.returncode}"
                print(f"[{_ts()} SOURCES] browser reader failed: {detail[:160]}")
            except Exception as e:
                print(f"[{_ts()} SOURCES] browser reader exception: {type(e).__name__}: {e}")
    return ""


def _load_source_cache() -> dict:
    try:
        if SOURCE_CACHE_PATH.exists():
            return json.loads(SOURCE_CACHE_PATH.read_text())
    except Exception as e:
        print(f"[{_ts()} SOURCES] source cache read failed: {e}")
    return {"searches": {}}


def _save_source_cache(cache: dict):
    try:
        SOURCE_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        print(f"[{_ts()} SOURCES] source cache write failed: {e}")


def _search_web(query: str, limit: int = 6) -> list:
    """Search the web and return a list of {title, url, query, engine} dicts.

    Engine priority:
      1. Mojeek — returns plain static HTML, no bot-blocking
      2. DuckDuckGo HTML — fallback; DDG increasingly blocks scrapers
      3. Bing — last resort; JS-heavy but sometimes useful
    """
    import html as _html
    import urllib.parse

    qenc = urllib.parse.quote(query)
    cache = _load_source_cache()
    cache_key = re.sub(r"\s+", " ", query.strip().lower())
    cached = cache.get("searches", {}).get(cache_key)
    if cached:
        age_seconds = time.time() - float(cached.get("saved_at", 0))
        if age_seconds < 7 * 24 * 60 * 60 and cached.get("results"):
            print(f"[{_ts()} SOURCES] search cache HIT: {query}")
            return cached.get("results", [])[:limit]

    # Each entry: (engine_name, fetch_url, [(href_group, title_group), ...])
    # Patterns must capture exactly 2 groups: (href, title_text).
    engines = [
        (
            "brave",
            f"https://search.brave.com/search?q={qenc}",
            [
                r'<a[^>]+href="(https?://[^"]{10,240})"[^>]*>(.*?)</a>',
            ],
        ),
        (
            "google_news",
            f"https://news.google.com/rss/search?q={qenc}&hl=en-US&gl=US&ceid=US:en",
            [],
        ),
        (
            "yahoo",
            f"https://search.yahoo.com/search?p={qenc}",
            [
                r'<a[^>]+href="([^"]{10,500})"[^>]*>(.*?)</a>',
            ],
        ),
        (
            "mojeek",
            f"https://www.mojeek.com/search?q={qenc}&safe=0",
            # Mojeek result links are plain <a href="https://...">Title text</a>
            # outside of nav/sidebar — match any external href with adjacent text.
            [r'href="(https?://(?!(?:www\.)?mojeek\.com)[^"]{10,200})"[^>]*>([^<]{5,120})'],
        ),
        (
            "duckduckgo",
            f"https://duckduckgo.com/html/?q={qenc}",
            [
                r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                r'class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                # newer DDG HTML layout
                r'href="(https?://[^"]{10,200})"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>',
            ],
        ),
        (
            "bing",
            f"https://www.bing.com/search?q={qenc}",
            [
                r'<h2[^>]*>\s*<a[^>]+href="(https?://[^"]{10,200})"[^>]*>(.*?)</a>',
                # Bing sometimes uses data-href instead of href
                r'data-href="(https?://[^"]{10,200})"[^>]*>\s*([^<]{5,120})',
            ],
        ),
    ]

    _SKIP_DOMAINS = frozenset([
        "duckduckgo.com", "bing.com", "microsoft.com",
        "google.com", "mojeek.com", "brave.com", "search.yahoo.com",
        "login.yahoo.com", "guce.yahoo.com", "blocksurvey.io",
        "buttondown.email", "blog.mojeek.com", "community.mojeek.com",
    ])

    def _clean_href(href: str) -> str:
        href = href.replace("&amp;", "&")
        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            qs     = urllib.parse.parse_qs(parsed.query)
            href   = qs.get("uddg", [href])[0]
        if "r.search.yahoo.com" in href and "/RU=" in href:
            try:
                encoded = href.split("/RU=", 1)[1].split("/RK=", 1)[0]
                href = urllib.parse.unquote(encoded)
            except Exception:
                pass
        return urllib.parse.unquote(href)

    seen    = set()
    results = []

    for engine, url, patterns in engines:
        if len(results) >= limit:
            break
        print(f"[{_ts()} SOURCES] searching {engine}: {url[:140]}")
        raw_html = _fetch_raw_url(url, timeout=12)
        if not raw_html:
            print(f"[{_ts()} SOURCES] {engine}: empty response (blocked or SSL error)")
            continue
        matched = 0
        if engine == "google_news":
            for item in re.findall(r"<item>(.*?)</item>", raw_html, re.I | re.S):
                title_m = re.search(r"<title>(.*?)</title>", item, re.I | re.S)
                link_m = re.search(r"<link>(https://news\.google\.com/rss/articles/[^<]+)</link>", item, re.I | re.S)
                if not title_m or not link_m:
                    continue
                href = _html.unescape(link_m.group(1)).strip()
                title = _strip_html_text(_html.unescape(title_m.group(1)))
                if href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "query": query, "engine": engine})
                matched += 1
                if len(results) >= limit:
                    break
            print(f"[{_ts()} SOURCES] {engine}: {matched} result(s) matched (html={len(raw_html)} bytes)")
            if len(results) >= limit:
                break
            continue
        for pattern in patterns:
            for m in re.finditer(pattern, raw_html, re.I | re.S):
                href, title_html = m.groups()
                href  = _clean_href(href)
                title = _strip_html_text(title_html)
                if not href.startswith("http") or href in seen:
                    continue
                domain = urllib.parse.urlparse(href).netloc.lower().lstrip("www.")
                if domain != "news.google.com" and any(skip in domain for skip in _SKIP_DOMAINS):
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "query": query, "engine": engine})
                matched += 1
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        print(f"[{_ts()} SOURCES] {engine}: {matched} result(s) matched (html={len(raw_html)} bytes)")
        relevant = [
            r for r in results
            if any(term.strip('"').lower() in (r.get("title", "") + " " + r.get("url", "")).lower()
                   for term in query.split()
                   if len(term.strip('"')) >= 4)
        ]
        if len(relevant) >= limit:
            # Got something from this engine — don't bother with lower-priority engines
            break

    if results:
        cache.setdefault("searches", {})[cache_key] = {
            "saved_at": time.time(),
            "query": query,
            "results": results[:12],
        }
        _save_source_cache(cache)

    return results


def _ddg_search(query: str, limit: int = 5) -> list:
    return _search_web(query, limit=limit)


def _fetch_wiki_citations(case_name: str) -> list:
    """Return a list of external URLs cited in a Wikipedia article.

    Uses the Wikipedia Action API (wikitext) so we get raw citation URLs without
    needing to scrape a rendered page. Returns [] on any error.
    """
    import json as _json, urllib.parse as _up, urllib.request as _ur, ssl as _ssl
    try:
        import certifi as _cf
        _ctx = _ssl.create_default_context(cafile=_cf.where())
    except Exception:
        _ctx = None
    try:
        api_url = (
            "https://en.wikipedia.org/w/api.php?action=query&titles="
            + _up.quote(case_name.replace(" ", "_"))
            + "&prop=revisions&rvprop=content&rvslots=main"
            + "&format=json&formatversion=2"
        )
        req = _ur.Request(api_url, headers={"User-Agent": "VerdictIn60/1.0 (contact@verdictin60.com)"})
        kw  = {"context": _ctx} if _ctx else {}
        with _ur.urlopen(req, timeout=12, **kw) as r:
            data = _json.loads(r.read())
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return []
        wikitext = (
            pages[0]
            .get("revisions", [{}])[0]
            .get("slots", {})
            .get("main", {})
            .get("content", "")
        )
        # Extract URLs from |url= parameters and bare [[url]] references.
        # Skip archive.org mirrors — we prefer the live source.
        urls_raw  = re.findall(r'url\s*=\s*(https?://[^\s|}\]]{10,250})', wikitext)
        urls_raw += re.findall(r'\[(https?://[^\s\]]{10,250})', wikitext)
        seen, urls = set(), []
        for u in urls_raw:
            u = u.strip().rstrip('.')
            if u in seen:
                continue
            seen.add(u)
            if "web.archive.org" in u:
                continue
            urls.append(u)
        print(f"[{_ts()} SOURCES] Wikipedia citations: {len(urls)} unique URLs for {case_name!r}")
        return urls
    except Exception as e:
        print(f"[{_ts()} SOURCES] _fetch_wiki_citations error: {e}")
        return []


def _search_courtlistener(case_name: str, limit: int = 5) -> list:
    """Search CourtListener for legal opinions mentioning the case.

    Returns a list of {title, url} dicts. CourtListener's HTML search is
    publicly accessible without authentication.
    """
    import urllib.parse as _up
    q   = _up.quote(f'"{case_name}"')
    url = f"https://www.courtlistener.com/?q={q}&type=o&order_by=score+desc"
    print(f"[{_ts()} SOURCES] CourtListener search: {url[:120]}")
    html = _fetch_raw_url(url, timeout=12)
    if not html:
        return []
    results = []
    for m in re.finditer(
        r'href="(/opinion/\d+/[a-z0-9-]+/)[^"]*"[^>]*>\s*(?:<[^>]+>)*\s*([^<]{3,120})',
        html, re.S
    ):
        path  = m.group(1)
        title = re.sub(r'\s+', ' ', m.group(2)).strip()
        if not title or title.startswith('<'):
            continue
        full_url = f"https://www.courtlistener.com{path}"
        if full_url not in {r['url'] for r in results}:
            results.append({"title": title[:80], "url": full_url})
            if len(results) >= limit:
                break
    print(f"[{_ts()} SOURCES] CourtListener: {len(results)} opinion(s) found")
    return results


# ── Source classification ─────────────────────────────────────────────────────
# Maps a URL + title to one of 5 tier labels.
# Tier 1 = Official, Tier 2 = Reporting, Tier 3 = Investigative,
# Tier 4 = Agency, Tier 5 = Encyclopedia.  Unrecognised = "Reference".

_TIER1_OFFICIAL = (
    ".gov", "police", "sheriff", "district-attorney", "districtattorney",
    "prosecutor", "justice.gov", "courts.gov", "supremecourt", "appeals",
    "coroner", "medical-examiner", "medicalexaminer", "prison", "corrections",
    "missingpersons", "namus.gov", "fbi.gov", "dea.gov",
    "bundesgericht", "staatsanwaltschaft", "lincolncountymt",
)
_TIER2_REPORTING = (
    "abcnews.go.com", "nbcnews.com", "cbsnews.com", "cnn.com",
    "apnews.com", "reuters.com", "bbc.co", "bbc.com",
    "courttv.com", "dateline", "48hours", "today.com", "people.com",
    "usatoday.com", "washingtonpost.com", "nytimes.com", "latimes.com",
    "theguardian.com", "chicagotribune.com", "nypost.com",
    # common local station patterns
    "wate.com", "wvlt.tv", "wbir.com", "wsmv.com", "wkrn.com",
    "nbcmontana.com", "kpax.com", "ktvq.com", "kulr8.com", "krtv.com",
    "montanarightnow.com", "flatheadbeacon.com", "dailyinterlake.com",
    "missoulian.com", "billingsgazette.com", "wset.com", "abcnews4.com",
)
_TIER3_INVESTIGATIVE = (
    "newyorker.com", "rollingstone.com", "propublica.org",
    "texasmonthly.com", "theatlantic.com", "vanityfair.com",
    "motherjones.com", "thedailybeast.com",
)
_TIER4_AGENCY = (
    "fbi.gov", "dea.gov", "interpol.int", "ncmec.org",
    "uscourts.gov", "courtlistener.com", "justia.com",
    "law.justia.com", "oyez.org", "findlaw.com", "caselaw.",
)
_TIER5_ENCYCLOPEDIA = (
    "britannica.com",
)


def _classify_source(url: str, title: str = "") -> str:
    """Return the tier label for a URL.  Wikipedia is always excluded externally."""
    hay = f"{url} {title}".lower()
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower().lstrip("www.")
    # Tier 4 legal databases checked before generic "official" so Justia etc.
    # aren't mis-tagged as Official.
    if any(m in hay for m in _TIER4_AGENCY):
        return "Agency"
    if any(m in hay for m in _TIER1_OFFICIAL):
        return "Official"
    if any(m in hay for m in _TIER2_REPORTING):
        return "Reporting"
    if any(m in hay for m in _TIER3_INVESTIGATIVE):
        return "Investigative"
    if any(m in hay for m in _TIER5_ENCYCLOPEDIA):
        return "Encyclopedia"
    if re.search(r"\.(gov|us)$", domain) or any(
        marker in domain for marker in ("sheriff", "police", "county", "da-", "districtattorney")
    ):
        return "Official"
    local_news_hints = (
        "news", "local", "breaking", "crime", "missing", "found", "rescue",
        "sheriff", "police", "investigation", "weather", "sports"
    )
    station_like = re.match(r"^(?:k|w)[a-z0-9]{2,5}\.(?:com|tv|org|net)$", domain)
    blog_hints = ("reddit", "youtube", "tiktok", "spotify", "podcast", "blogspot", "medium.com")
    if any(h in domain for h in blog_hints):
        return "Reference"
    if station_like or any(h in hay for h in local_news_hints):
        return "Reporting"
    return "Reference"


def gather_verification_sources(case_name: str, original_context: str,
                                wiki_title: str = "", wiki_facts: str = "") -> list:
    """Gather sources using a strict 5-tier priority system.

    Strategy (in order):
      1. Official/government/court-oriented web searches
      2. CourtListener direct legal search
      3. Extract citation URLs from the Wikipedia article as discovery leads
      4. Reputable reporting and investigative searches

    Tier labels (for source_section_for_caption):
      Official      — .gov, police, DA, court records, medical examiner
      Reporting     — AP, Reuters, BBC, ABC/NBC/CBS/CNN, local news
      Investigative — New Yorker, Rolling Stone, ProPublica, Texas Monthly
      Agency        — FBI/DEA/Interpol/NCMEC, CourtListener, Justia, Oyez
      Encyclopedia  — Britannica (orientation only, never cited as a source)

    Wikipedia is orientation context only — never returned as a citable source.
    Stops early once ≥2 Tier-1/2 (Official + Reporting) sources are secured.
    """
    first_name = case_name.split()[0].lower() if case_name.split() else ""
    last_name  = case_name.split()[-1].lower() if case_name.split() else ""
    sources: list  = []
    seen_urls: set = set()

    def _normalize(s: str) -> str:
        """Lowercase + strip accents for accent-insensitive matching."""
        import unicodedata
        return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

    _name_norm      = _normalize(case_name)
    _first_norm     = _normalize(first_name)
    _last_norm      = _normalize(last_name)
    _wiki_title_norm = _normalize(wiki_title or "")

    context_terms = []
    for m in re.finditer(
        r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'.-]{2,}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'.-]{2,}){0,2}\b",
        original_context[:1400]
    ):
        term = m.group(0).strip()
        norm = _normalize(term)
        if len(norm) < 4:
            continue
        if norm in {
            "according", "investigators", "january", "february", "march",
            "april", "june", "july", "august", "september", "october",
            "november", "december"
        }:
            continue
        if norm not in context_terms:
            context_terms.append(norm)
        if len(context_terms) >= 10:
            break

    def _name_in(text: str) -> bool:
        tn = _normalize(text)
        if _name_norm and _name_norm in tn:
            return True
        if _wiki_title_norm and _wiki_title_norm in tn:
            return True
        if _first_norm and _last_norm and _first_norm in tn and _last_norm in tn:
            return True
        if _last_norm and len(_last_norm) >= 5 and _last_norm in tn:
            return True
        context_hits = sum(1 for term in context_terms if term in tn)
        return context_hits >= 2

    def _add_source(url: str, title: str, tier_label: str) -> bool:
        """Fetch a URL, check it mentions the case, classify and append. Returns True if added."""
        if url in seen_urls or "wikipedia.org" in url.lower():
            return False
        seen_urls.add(url)
        print(f"[{_ts()} SOURCES] fetching ({tier_label}): {url[:110]}")
        raw = _fetch_raw_url(url, timeout=8)
        reader = "direct"
        text = _extract_readable_text(raw)[:5000] if raw else ""
        if raw and (_looks_like_block_page(text) or len(text) < 450):
            print(f"[{_ts()} SOURCES] direct fetch looked blocked/thin, trying browser reader: {url[:90]}")
            raw = ""
            text = ""
        if not raw:
            browser_raw = _fetch_browser_rendered_html(url, timeout=24)
            browser_text = _extract_readable_text(browser_raw)[:5000] if browser_raw else ""
            if browser_raw and not _looks_like_block_page(browser_text) and len(browser_text) >= 450:
                raw = browser_raw
                text = browser_text
                reader = "browser"
            else:
                print(f"[{_ts()} SOURCES] empty/blocked response after browser reader: {url[:90]}")

        if not raw:
            if not _name_in(f"{title} {url}"):
                print(f"[{_ts()} SOURCES] blocked source not case-specific, skipping: {url[:90]}")
                return False
            kind = _classify_source(url, title)
            sources.append({
                "title": title or url[:80],
                "url": url,
                "kind": kind,
                "tier": kind,
                "text": "",
                "blocked": True,
                "inaccessible_reason": "Source found but inaccessible to the app",
            })
            return False
        if not title:
            title = _page_title(raw)
        if not _name_in(f"{title} {url} {text}"):
            print(f"[{_ts()} SOURCES] case name not in page, skipping: {url[:90]}")
            return False
        kind = _classify_source(url, title)
        sources.append({
            "title": title or url[:80],
            "url": url,
            "kind": kind,
            "tier": kind,
            "text": text[:4500],
            "blocked": False,
            "reader": reader,
        })
        print(f"[{_ts()} SOURCES] ADDED ({kind}, {reader}): {title[:65]}")
        return True

    def _add_discovered_source(url: str, title: str, tier_label: str) -> bool:
        """Keep a case-specific search result when full-page fetch is unavailable."""
        if url in seen_urls or "wikipedia.org" in url.lower():
            return False
        if not _name_in(f"{title} {url}"):
            return False
        kind = _classify_source(url, title)
        if kind == "Reference":
            return False
        seen_urls.add(url)
        sources.append({
            "title": title or url[:80],
            "url": url,
            "kind": kind,
            "tier": kind,
            "text": "",
            "blocked": True,
            "discovered_only": True,
            "inaccessible_reason": "Source discovered in search results; full page was not accessible to the app",
        })
        print(f"[{_ts()} SOURCES] DISCOVERED ({kind}): {(title or url)[:65]}")
        return True

    def _high_quality_count() -> int:
        return sum(
            1 for s in sources
            if s.get("kind") in ("Official", "Reporting") and not s.get("blocked")
        )

    def _accessible_count() -> int:
        return sum(1 for s in sources if not s.get("blocked") and s.get("tier") != "Wikipedia")

    def _is_discovery_only_result(result: dict) -> bool:
        return (
            result.get("engine") == "google_news"
            or "news.google.com/rss/articles/" in result.get("url", "")
        )

    # ── Step 1: Official / legal web search ──────────────────────────────────
    print(f"[{_ts()} SOURCES] === Step 1: Official/legal source search ===")
    context = original_context[:1800]
    location_terms = []
    year_terms = re.findall(r"\b(?:18|19|20)\d{2}\b", context)
    for word in (
        "New York", "Manhattan", "Long Island", "Tennessee", "Knoxville",
        "Florida", "Texas", "California", "Pennsylvania", "Philadelphia",
        "Ohio", "Georgia", "North Carolina", "South Carolina", "Virginia",
        "Kentucky", "Missouri", "Illinois", "Germany", "North Korea",
        "Montana", "Bull Lake", "Lincoln County",
    ):
        if re.search(rf"\b{re.escape(word)}\b", context, re.I):
            location_terms.append(word)

    official_queries = [
        ("Official", f'"{case_name}" police sheriff prosecutor "district attorney" court'),
        ("Official", f'"{case_name}" indictment sentencing appeal "court records"'),
        ("Official", f'"{case_name}" "sheriff" "missing"'),
        ("Official", f'"{case_name}" "Lincoln County Sheriff"'),
        ("Agency", f'"{case_name}" CourtListener Justia FindLaw caselaw'),
    ]
    if year_terms:
        official_queries.append(("Official", f'"{case_name}" "{year_terms[0]}" court police prosecutor'))
    for loc in location_terms[:3]:
        official_queries.append(("Official", f'"{case_name}" "{loc}" court police prosecutor'))

    for tier_label, query in official_queries:
        print(f"[{_ts()} SOURCES] query ({tier_label}): {query}")
        for result in _search_web(query, limit=4):
            if _is_discovery_only_result(result):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            elif not _add_source(result["url"], result.get("title", ""), tier_label):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            if _high_quality_count() >= 2:
                print(f"[{_ts()} SOURCES] Early exit after official/legal search: {_high_quality_count()} Tier-1/2")
                return sources

    # ── Step 2: CourtListener direct search ───────────────────────────────────
    print(f"[{_ts()} SOURCES] === Step 2: CourtListener direct search ===")
    for cl_result in _search_courtlistener(case_name, limit=4):
        _add_source(cl_result["url"], cl_result["title"], "Agency")
        if _high_quality_count() >= 2:
            print(f"[{_ts()} SOURCES] Early exit after CourtListener: {_high_quality_count()} Tier-1/2")
            return sources

    # ── Step 3: Wikipedia citations ───────────────────────────────────────────
    # Wikipedia's wikitext contains curated references with real source URLs —
    # BBC, AP, Reuters, CNN, .gov sites, etc. — all without needing search engines.
    lookup_name = wiki_title or case_name
    print(f"[{_ts()} SOURCES] === Step 3: Wikipedia citations for {lookup_name!r} ===")
    wiki_urls = _fetch_wiki_citations(lookup_name)

    # Classify each citation URL and process highest tiers first
    tier_order_map = {"Official": 0, "Reporting": 1, "Investigative": 2, "Agency": 3,
                      "Encyclopedia": 4, "Reference": 5}
    def _url_tier_priority(url: str) -> int:
        t = _classify_source(url, "")
        return tier_order_map.get(t, 5)

    wiki_urls_sorted = sorted(wiki_urls, key=_url_tier_priority)

    for url in wiki_urls_sorted:
        tier_label = _classify_source(url, "")
        if tier_label == "Encyclopedia":
            continue   # Britannica etc — skip, not useful as an independent source
        # "Reference" = unrecognised domain but still a real citation from Wikipedia;
        # attempt it and let _add_source decide if the content is relevant.
        _add_source(url, "", tier_label)
        if _high_quality_count() >= 2:
            print(f"[{_ts()} SOURCES] Early exit after Wiki citations: {_high_quality_count()} Tier-1/2")
            return sources

    # ── Step 4: Reporting / investigative search fallback ───────────────────
    # This is intentionally after citations + legal search. It catches cases
    # where Wikipedia cites blocked newspaper pages, or where a local station /
    # court page is discoverable but not cited.
    print(f"[{_ts()} SOURCES] === Step 4: Reporting/investigative search ===")
    query_plan = [
        ("Reporting", f'"{case_name}"'),
        ("Reporting", f'"{case_name}" missing found investigation'),
        ("Reporting", f'"{case_name}" AP Reuters BBC ABC NBC CBS CNN'),
        ("Reporting", f'"{case_name}" CNN NBC CBS ABC'),
        ("Reporting", f'"{case_name}" "NBC Montana" KPAX KTVQ KULR KRTV'),
        ("Reporting", f'"{case_name}" local news newspaper "New York Times"'),
        ("Investigative", f'"{case_name}" ProPublica "The New Yorker" "Rolling Stone" documentary'),
    ]
    for loc in location_terms[:3]:
        query_plan.insert(1, ("Reporting", f'"{case_name}" "{loc}" news newspaper'))
    if year_terms:
        query_plan.insert(1, ("Reporting", f'"{case_name}" "{year_terms[0]}" news newspaper'))

    for tier_label, query in query_plan:
        print(f"[{_ts()} SOURCES] query ({tier_label}): {query}")
        for result in _search_web(query, limit=5):
            if _is_discovery_only_result(result):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            elif not _add_source(result["url"], result.get("title", ""), tier_label):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            if _high_quality_count() >= 2:
                print(f"[{_ts()} SOURCES] Early exit after reporting search: {_high_quality_count()} Tier-1/2")
                return sources

    print(f"[{_ts()} SOURCES] Search complete: {len(sources)} source(s), "
          f"{_high_quality_count()} high-quality, {_accessible_count()} accessible")

    # ── Step 4: Wikipedia orientation fallback (last resort) ──────────────────
    if wiki_facts and not any(not s.get("blocked") for s in sources):
        wiki_url = "https://en.wikipedia.org/wiki/" + (wiki_title or case_name).replace(" ", "_")
        sources.append({
            "title": wiki_title or f"Wikipedia: {case_name}",
            "url": wiki_url,
            "kind": "Orientation only",
            "tier": "Wikipedia",
            "text": wiki_facts[:5000],
        })

    return sources


def format_sources_for_prompt(sources: list) -> str:
    """Format sources for the AI caption prompt, excluding pure orientation entries."""
    usable = [
        s for s in sources
        if s.get("tier") not in ("Wikipedia",) and not s.get("blocked")
    ]
    if not usable:
        # Fall back to Wikipedia orientation if it's all we have
        usable = [s for s in sources if not s.get("blocked")]
    if not usable:
        return "No independent sources found."
    blocks = []
    for i, src in enumerate(usable, 1):
        blocks.append(
            f"[{i}] {src.get('title','Source')} "
            f"(Tier: {src.get('tier','?')} / {src.get('kind','Reference')})\n"
            f"URL: {src.get('url','')}\n"
            f"TEXT: {src.get('text','')[:2500]}"
        )
    return "\n\n".join(blocks)


def format_blocked_sources_for_prompt(sources: list) -> str:
    blocked = [s for s in sources if s.get("blocked")]
    if not blocked:
        return "None."
    lines = []
    for src in blocked[:8]:
        lines.append(
            f"- {src.get('title','Source')} ({src.get('kind','Reference')})\n"
            f"  URL: {src.get('url','')}\n"
            f"  Reason: {src.get('inaccessible_reason','Inaccessible')}"
        )
    return "\n".join(lines)


def verification_confidence(sources: list) -> tuple[str, str]:
    accessible = [
        s for s in sources
        if not s.get("blocked") and s.get("tier") != "Wikipedia"
    ]
    official = [s for s in accessible if s.get("kind") == "Official"]
    reporting = [s for s in accessible if s.get("kind") == "Reporting"]
    agency = [s for s in accessible if s.get("kind") == "Agency"]
    investigative = [s for s in accessible if s.get("kind") == "Investigative"]
    reliable = official + reporting + agency + investigative
    blocked = [s for s in sources if s.get("blocked")]
    wiki_only = bool(sources) and not accessible and any(s.get("tier") == "Wikipedia" for s in sources)

    if official and len(reliable) >= 2:
        return "High", "Official source plus multiple accessible sources."
    if len(reporting) >= 2 or (reporting and (official or agency or investigative)):
        return "Medium", "Multiple accessible sources, including reputable reporting."
    if reporting or agency or investigative:
        return "Low", "Only one accessible reliable source was found."
    if blocked and not accessible:
        return "Low", "Reliable-looking sources were discovered but inaccessible."
    if wiki_only:
        return "Low", "Only encyclopedia orientation was accessible."
    return "Very low", "Only the original video caption or weak context is available."


def build_verified_fact_sheet(case_name: str, sources: list) -> str:
    accessible = [
        s for s in sources
        if not s.get("blocked") and s.get("tier") != "Wikipedia"
    ]
    lines = [
        f"Case title: {case_name}",
        "Victim: Use only if explicitly supported by accessible sources.",
        "Suspect: Use only if explicitly supported by accessible sources.",
        "Location: Use only if explicitly supported by accessible sources.",
        "Year: Use only if explicitly supported by accessible sources.",
        "Crime type: Use only if explicitly supported by accessible sources.",
        "Discovery: Use only if explicitly supported by accessible sources.",
        "Investigation: Use only if explicitly supported by accessible sources.",
        "Court outcome: Use only if explicitly supported by accessible sources.",
        "Sentence: Use only if explicitly supported by accessible sources.",
        "Reliable source URLs:",
    ]
    if accessible:
        for src in accessible[:8]:
            lines.append(f"- {src.get('url','')}")
    else:
        lines.append("- No accessible reliable source found.")
    lines.extend([
        "Unverified details: Any detail found only in the original video caption.",
        "Conflicting details: If sources disagree, phrase generally or omit the detail.",
    ])
    return "\n".join(lines)


def source_section_for_caption(sources: list) -> str:
    """Build the Research & Verification block for the end of every caption.

    Format:
        ━━━━━━━━━━━━━━━
        Research & Verification

        Official:
        • Source name

        Reporting:
        • Source name

    Wikipedia is never listed. If only Wikipedia was found, a note is added instead.
    """
    buckets = {"Official": [], "Reporting": [], "Investigative": [], "Agency": []}
    discovered = {"Official": [], "Reporting": [], "Investigative": [], "Agency": []}
    has_real_sources = False

    def _display_source_name(src: dict) -> str:
        title = src.get("title", "Source").strip() or "Source"
        if src.get("discovered_only"):
            # Google News titles usually end with " - Outlet". Use the outlet
            # name in the public caption so the research block stays polished.
            outlet_m = re.search(r"\s+-\s+([^-\n]{3,60})$", title)
            if outlet_m:
                return outlet_m.group(1).strip()
        return re.split(r"\s+(?:[|—])\s+", title, maxsplit=1)[0].strip() or title

    for src in sources:
        kind = src.get("kind", "Reference")
        tier = src.get("tier", "")
        if src.get("blocked"):
            if src.get("discovered_only") and kind in discovered:
                short = _display_source_name(src)
                if short not in discovered[kind]:
                    discovered[kind].append(short[:70])
            continue
        if tier == "Wikipedia" or kind == "Orientation only":
            continue
        has_real_sources = True
        bucket_key = kind if kind in buckets else None
        if bucket_key is None:
            continue
        short = _display_source_name(src)
        if short not in buckets[bucket_key]:
            buckets[bucket_key].append(short[:70])

    lines = ["━━━━━━━━━━━━━━━", "Research & Verification", ""]
    if buckets["Official"]:
        lines.append("Official:")
        lines.extend(f"• {s}" for s in buckets["Official"][:4])
        lines.append("")
    else:
        lines.append("Official:")
        lines.append("• Public official records were not available in the accessible review materials.")
        lines.append("")
    if buckets["Reporting"]:
        lines.append("Reporting:")
        lines.extend(f"• {s}" for s in buckets["Reporting"][:5])
        lines.append("")
    elif discovered["Reporting"]:
        lines.append("Reporting:")
        lines.extend(f"• {s} (source lead; full article access limited)" for s in discovered["Reporting"][:5])
        lines.append("")
    else:
        lines.append("Reporting:")
        lines.append("• Additional reputable reporting review recommended.")
        lines.append("")
    if buckets["Investigative"]:
        lines.append("Investigative:")
        lines.extend(f"• {s}" for s in buckets["Investigative"][:3])
        lines.append("")
    if buckets["Agency"]:
        lines.append("Agency:")
        lines.extend(f"• {s}" for s in buckets["Agency"][:4])
        lines.append("")

    if not has_real_sources and not any(discovered.values()):
        has_wiki = any(s.get("tier") == "Wikipedia" for s in sources)
        if has_wiki:
            lines.append("Reference note:")
            lines.append("• Encyclopedia material used for orientation only.")

    return "\n".join(lines)


# ── Shared canvas animation drawing ──────────────────────────────────────────
def _draw_anim(c, state, phase, status_txt, idle_hint=""):
    import math as _math
    cw = c.winfo_width()
    ch = c.winfo_height()
    if cw < 10:
        return
    c.delete("all")

    cx = cw // 2

    FOLDER_MID   = "#9B7A2E"
    FOLDER_DARK  = "#5C4010"
    FOLDER_LIGHT = "#C4A04A"
    PAGE_COL     = "#E8E4D8"
    GAVEL_HEAD   = "#DDDDDD"
    GAVEL_SHADE  = "#AAAAAA"
    HANDLE_COL   = "#8B6030"

    fw, fh = 224, 78
    fy_base = 55
    fx1, fy1 = cx - fw // 2, fy_base
    fx2, fy2 = cx + fw // 2, fy_base + fh
    tw, th = 68, 17
    tx1, ty1 = fx1 + 14, fy1 - th
    tx2, ty2 = tx1 + tw, fy1

    open_amt = 0.0
    if state == "processing":
        open_amt = max(0.0, _math.sin(phase * _math.pi * 2)) ** 0.6
    elif state == "scheduling":
        open_amt = 0.75 + 0.05 * _math.sin(phase * _math.pi * 4)
    elif state == "success":
        open_amt = max(0.0, 0.6 - phase * 1.7) if phase < 0.35 else 0.0

    if open_amt > 0.04:
        rise = int(open_amt * 44)
        for i, (x_off, col) in enumerate([(-28, "#D4D0C4"), (0, PAGE_COL), (28, "#DEDAD0")]):
            c.create_rectangle(
                cx + x_off - 20, fy1 - rise + 18 + i * 2,
                cx + x_off + 20, fy1 + 14,
                fill=col, outline="#B0AC9C", width=1
            )
            for li in range(3):
                ly = fy1 - rise + 26 + i * 2 + li * 6
                if ly < fy1 + 10:
                    c.create_line(cx + x_off - 13, ly, cx + x_off + 13, ly,
                                  fill="#888880", width=1)

    c.create_rectangle(fx1, fy1, fx2, fy2,
                       fill=FOLDER_MID, outline=FOLDER_DARK, width=2)
    c.create_rectangle(fx1 + 2, fy1 + 2, fx2 - 2, fy1 + 10,
                       fill=FOLDER_LIGHT, outline="")
    c.create_polygon(
        tx1 + 6, ty1, tx2, ty1,
        tx2, ty2, tx1, ty2,
        fill=FOLDER_LIGHT, outline=FOLDER_DARK, width=2
    )

    alpha_text = max(0.0, 1.0 - open_amt * 2.5)
    if alpha_text > 0.3:
        gray_val = int(0xFF * alpha_text)
        txt_col  = f"#{gray_val:02x}{gray_val:02x}{gray_val:02x}"
        c.create_text(cx, fy1 + fh // 2 + 2,
                      text="CASE FILE", font=("Helvetica", 10, "bold"), fill=txt_col)

    if state in ("processing", "scheduling"):
        pulse = (_math.sin(phase * _math.pi * 6) + 1) / 2
        r = 4 + int(pulse * 2)
        dx, dy = fx2 - 14, fy1 + 10
        c.create_oval(dx - r, dy - r, dx + r, dy + r, fill=CRIMSON, outline="")

    if state == "success":
        impact_phase = min(1.0, phase / 0.35)
        gavel_y = int(-60 + impact_phase * (fy1 - 22 + 60))
        if 0.34 < phase < 0.60:
            c.configure(highlightbackground=CRIMSON, highlightthickness=2)
        else:
            c.configure(highlightbackground="#2a2a2a", highlightthickness=1)
        gh_w, gh_h = 80, 24
        ghx1, ghy1 = cx - gh_w // 2, gavel_y
        ghx2, ghy2 = cx + gh_w // 2, gavel_y + gh_h
        c.create_rectangle(ghx1, ghy1, ghx2, ghy2,
                           fill=GAVEL_HEAD, outline=GAVEL_SHADE, width=2)
        c.create_rectangle(ghx1 + 3, ghy1 + 3, ghx2 - 3, ghy1 + 8,
                           fill="#F0F0F0", outline="")
        hx1, hy1 = cx + 28, gavel_y + 16
        hx2, hy2 = cx + 28 + 36, gavel_y + 16 + 55
        c.create_polygon(
            hx1, hy1, hx1 + 10, hy1,
            hx2 + 10, hy2, hx2, hy2,
            fill=HANDLE_COL, outline=FOLDER_DARK, width=1
        )
        if phase > 0.45:
            alpha = min(1.0, (phase - 0.45) / 0.25)
            gray  = int(0xFF * alpha)
            scheduled_col = f"#{gray:02x}{gray:02x}{gray:02x}"
            c.create_text(cx, fy2 + 28,
                          text="✓  SCHEDULED",
                          font=("Helvetica", 15, "bold"),
                          fill=scheduled_col)

    if status_txt and state not in ("success",):
        clean = status_txt.lstrip("⏳📅🔴✅✓ ")
        c.create_text(cx, fy2 + 20, text=clean,
                      font=("Courier", 9), fill=LIGHT_GRAY,
                      width=cw - 40)
    elif state == "idle" and not status_txt:
        c.create_text(cx, fy2 + 20, text=idle_hint,
                      font=("Courier", 9), fill="#444444")
    elif state == "error" and status_txt:
        clean = status_txt.lstrip("✗✓ ")
        c.create_text(cx, fy2 + 20, text=clean,
                      font=("Courier", 9), fill=ERROR_RED,
                      width=cw - 40)


# ── Main App ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VerdictIn60 Reel Editor")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(800, 700)
        self.selected_file  = None
        self._processing    = False
        self._last_bg_size  = (0, 0)
        self._batch_rows    = []   # list of dicts, one per queued video
        self._batch_running = False
        self._pending_upload_url  = None   # used by retry-schedule flow
        self._pending_caption     = None
        self._pending_due_dt      = None
        self._library = case_library.CaseLibrary(Path(__file__).parent)

        self._build_ui()
        self._check_ffmpeg()
        self.after(0, self._maximize)
        self.after(500, self._check_model_installed)

    def _maximize(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

    # ── Root layout ───────────────────────────────────────────────────────────

    def _build_ui(self):
        CONTENT_W = 720

        self._bg = tk.Canvas(self, bg=BG, highlightthickness=0)
        self._bg.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.bind("<Configure>", self._on_resize)

        wrapper = tk.Frame(self, bg=BG)
        wrapper.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        tk.Frame(wrapper, bg=BG).pack(side="left", fill="both", expand=True)
        self._outer = outer = tk.Frame(wrapper, bg=BG, width=CONTENT_W)
        outer.pack(side="left", fill="both")
        outer.pack_propagate(False)
        tk.Frame(wrapper, bg=BG).pack(side="right", fill="both", expand=True)

        # ── Shared header ─────────────────────────────────────────────────────
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")

        # Top crimson accent bar
        tk.Frame(header, bg=CRIMSON, height=3).pack(fill="x")

        logo_area = tk.Frame(header, bg=BG)
        logo_area.pack(fill="x", pady=(24, 0))

        logo_loaded = False
        try:
            from PIL import Image, ImageTk
            raw = Image.open(LOGO_PATH)
            raw.thumbnail((180, 90), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(raw)
            tk.Label(logo_area, image=self._logo_img, bg=BG).pack()
            logo_loaded = True
        except Exception:
            pass

        if not logo_loaded:
            tk.Label(logo_area, text="VERDICTIN60",
                     font=("Helvetica", 32, "bold"), fg=WHITE, bg=BG).pack()

        tk.Label(header, text="N E W  C A S E .  E V E R Y  D A Y .",
                 font=("Helvetica", 9, "bold"), fg=CRIMSON, bg=BG).pack(pady=(6, 0))

        tk.Frame(header, bg="#1a1a1a", height=1).pack(fill="x", pady=(16, 0))

        # ── Tab switcher ──────────────────────────────────────────────────────
        tab_bar = tk.Frame(outer, bg=BG)
        tab_bar.pack(fill="x", padx=30, pady=(14, 0))

        self._tab_single_btn = _make_lbtn(
            tab_bar, "SINGLE", lambda: self._switch_tab("single"),
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 10, "bold"), pady=10, padx=24
        )
        self._tab_single_btn.pack(side="left")

        self._tab_batch_btn = _make_lbtn(
            tab_bar, "BATCH", lambda: self._switch_tab("batch"),
            bg="#111111", fg="#555555", hover_bg="#1a1a1a", hover_fg="#AAAAAA",
            normal_fg="#555555", font=("Helvetica", 10, "bold"), pady=10, padx=24
        )
        self._tab_batch_btn.pack(side="left", padx=(2, 0))

        self._tab_url_btn = _make_lbtn(
            tab_bar, "URL IMPORT", lambda: self._switch_tab("url"),
            bg="#111111", fg="#555555", hover_bg="#1a1a1a", hover_fg="#AAAAAA",
            normal_fg="#555555", font=("Helvetica", 10, "bold"), pady=10, padx=24
        )
        self._tab_url_btn.pack(side="left", padx=(2, 0))

        self._tab_library_btn = _make_lbtn(
            tab_bar, "LIBRARY", lambda: self._switch_tab("library"),
            bg="#111111", fg="#555555", hover_bg="#1a1a1a", hover_fg="#AAAAAA",
            normal_fg="#555555", font=("Helvetica", 10, "bold"), pady=10, padx=24
        )
        self._tab_library_btn.pack(side="left", padx=(2, 0))

        self._tab_recovery_btn = _make_lbtn(
            tab_bar, "RECOVERY", lambda: self._switch_tab("recovery"),
            bg="#111111", fg="#555555", hover_bg="#1a1a1a", hover_fg="#AAAAAA",
            normal_fg="#555555", font=("Helvetica", 10, "bold"), pady=10, padx=24
        )
        self._tab_recovery_btn.pack(side="left", padx=(2, 0))

        tk.Frame(outer, bg="#2a2a2a", height=1).pack(fill="x", padx=30, pady=(6, 0))

        # ── Tab content frames ────────────────────────────────────────────────
        self._single_frame  = tk.Frame(outer, bg=BG)
        self._batch_frame   = tk.Frame(outer, bg=BG)
        self._url_frame     = tk.Frame(outer, bg=BG)
        self._library_frame = tk.Frame(outer, bg=BG)
        self._recovery_frame = tk.Frame(outer, bg=BG)
        self._single_frame.pack(fill="both", expand=True)
        # batch / url / library frames hidden initially

        self._build_single_tab(self._single_frame)
        self._build_batch_tab(self._batch_frame)
        self._build_url_tab(self._url_frame)
        self._build_library_tab(self._library_frame)
        self._build_recovery_tab(self._recovery_frame)

        # ── Shared footer ─────────────────────────────────────────────────────
        self._build_footer(outer)

    def _switch_tab(self, tab: str):
        for f in (self._single_frame, self._batch_frame,
                  self._url_frame, self._library_frame, self._recovery_frame):
            f.pack_forget()
        for btn in (self._tab_single_btn, self._tab_batch_btn,
                    self._tab_url_btn, self._tab_library_btn, self._tab_recovery_btn):
            btn.config(bg="#111111", fg="#555555")
        if tab == "single":
            self._single_frame.pack(fill="both", expand=True)
            self._tab_single_btn.config(bg=CRIMSON, fg=WHITE)
        elif tab == "batch":
            self._batch_frame.pack(fill="both", expand=True)
            self._tab_batch_btn.config(bg=CRIMSON, fg=WHITE)
        elif tab == "url":
            self._url_frame.pack(fill="both", expand=True)
            self._tab_url_btn.config(bg=CRIMSON, fg=WHITE)
        elif tab == "library":
            self._library_frame.pack(fill="both", expand=True)
            self._tab_library_btn.config(bg=CRIMSON, fg=WHITE)
            self._lib_tab.refresh()
        elif tab == "recovery":
            self._recovery_frame.pack(fill="both", expand=True)
            self._tab_recovery_btn.config(bg=CRIMSON, fg=WHITE)

    # ── Single tab ────────────────────────────────────────────────────────────

    def _build_recovery_tab(self, parent):
        PAD = 36
        inner = tk.Frame(parent, bg=BG)
        inner.pack(fill="both", expand=True, padx=PAD, pady=(24, 0))

        tk.Label(inner, text="RECOVERY ASSISTANT",
                 bg=BG, fg=WHITE, font=("Helvetica", 16, "bold")).pack(anchor="w")
        tk.Label(
            inner,
            text="Local rule-based diagnostics. Repairs always require approval.",
            bg=BG, fg=LIGHT_GRAY, font=("Helvetica", 10),
            wraplength=640, justify="left"
        ).pack(anchor="w", pady=(4, 14))

        btn_row = tk.Frame(inner, bg=BG)
        btn_row.pack(fill="x", pady=(0, 12))
        _make_lbtn(
            btn_row, "SCAN ENTIRE APPLICATION", self._recovery_run_scan,
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 11, "bold"), pady=12, padx=18
        ).pack(side="left")

        self._recovery_overall = tk.Label(
            inner, text="Status: not scanned yet",
            bg=BG, fg=LIGHT_GRAY, font=("Helvetica", 10, "bold")
        )
        self._recovery_overall.pack(anchor="w", pady=(0, 10))

        self._recovery_results = tk.Frame(inner, bg=BG)
        self._recovery_results.pack(fill="both", expand=True)

    def _recovery_run_scan(self):
        for child in self._recovery_results.winfo_children():
            child.destroy()
        issues = scan_recovery_health()
        attention = [i for i in issues if i["severity"] != "ok"]
        overall = "Attention Required" if attention else "Healthy"
        self._recovery_overall.config(
            text=f"Application Health: {overall}",
            fg=ERROR_RED if attention else "#2d8a4e"
        )
        for issue in issues:
            self._recovery_add_row(issue)

    def _recovery_add_row(self, issue: dict):
        severity = issue.get("severity", "ok")
        accent = "#2d8a4e" if severity == "ok" else CRIMSON
        row = tk.Frame(
            self._recovery_results, bg="#101010",
            highlightthickness=1, highlightbackground="#2a2a2a"
        )
        row.pack(fill="x", pady=(0, 8))

        left = tk.Frame(row, bg="#101010")
        left.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        tk.Label(left, text=f"{issue['area']}  ·  {issue['status']}",
                 bg="#101010", fg=accent,
                 font=("Helvetica", 10, "bold")).pack(anchor="w")
        tk.Label(left, text=issue["problem"],
                 bg="#101010", fg=WHITE,
                 font=("Helvetica", 10), wraplength=470,
                 justify="left").pack(anchor="w", pady=(3, 0))
        tk.Label(left, text=issue["why"],
                 bg="#101010", fg=LIGHT_GRAY,
                 font=("Helvetica", 9), wraplength=470,
                 justify="left").pack(anchor="w", pady=(3, 0))

        if issue.get("action"):
            _make_lbtn(
                row, "REPAIR", lambda i=issue: self._recovery_confirm_repair(i),
                bg="#1a1a1a", fg=WHITE, hover_bg="#2a2a2a",
                font=("Helvetica", 9, "bold"), pady=8, padx=14
            ).pack(side="right", padx=12)

    def _recovery_confirm_repair(self, issue: dict):
        dlg = tk.Toplevel(self, bg=BG)
        dlg.title("Repair Available")
        dlg.geometry("520x360")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.update_idletasks()
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"520x360+{(sw-520)//2}+{(sh-360)//2}")

        tk.Label(dlg, text="REPAIR AVAILABLE",
                 bg=BG, fg=CRIMSON,
                 font=("Helvetica", 12, "bold")).pack(anchor="w", padx=24, pady=(20, 8))
        msg = (
            f"Problem\n{issue['problem']}\n\n"
            f"Why it happened\n{issue['why']}\n\n"
            f"Recommended repair\n{issue.get('repair') or 'Manual review is recommended.'}\n\n"
            "Approval required\nNo repair will run unless you approve it."
        )
        tk.Label(dlg, text=msg, bg=BG, fg=WHITE,
                 font=("Helvetica", 10), justify="left",
                 wraplength=460).pack(anchor="w", padx=24)

        result_lbl = tk.Label(dlg, text="", bg=BG, fg=LIGHT_GRAY,
                              font=("Helvetica", 9), wraplength=460,
                              justify="left")
        result_lbl.pack(anchor="w", padx=24, pady=(10, 0))

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(side="bottom", fill="x", padx=24, pady=20)

        def _approve():
            result, verification = self._recovery_apply_repair(issue)
            result_lbl.config(text=f"{result}\n{verification}", fg="#2d8a4e")
            log_recovery_event(issue["problem"], issue["area"], True, result, verification)
            self.after(600, self._recovery_run_scan)

        def _cancel():
            log_recovery_event(issue["problem"], issue["area"], False, "Repair cancelled.", "No changes made.")
            dlg.destroy()

        _make_lbtn(
            btn_row, "APPROVE", _approve,
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 10, "bold"), pady=10
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        _make_lbtn(
            btn_row, "CANCEL", _cancel,
            bg="#2a2a2a", fg=WHITE, hover_bg="#3a3a3a",
            font=("Helvetica", 10, "bold"), pady=10
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _recovery_apply_repair(self, issue: dict) -> tuple[str, str]:
        action = issue.get("action", "")
        if action == "create_missing_folders":
            ASSETS_DIR.mkdir(exist_ok=True)
            OUTPUT_DIR.mkdir(exist_ok=True)
            ok = ASSETS_DIR.exists() and OUTPUT_DIR.exists()
            return (
                "Missing folders were created.",
                "✓ Folder check successful." if ok else "Verification failed: one or more folders are still missing."
            )
        if action == "open_settings":
            SettingsDialog(self)
            return "Settings opened for review.", "✓ No files or posts were modified."
        if action == "open_url_import":
            self._switch_tab("url")
            self._url_check_ollama_status()
            return "URL Import opened.", "✓ You can review the Ollama setup options there."
        if action == "show_ytdlp_install":
            self._switch_tab("url")
            self._url_show_install_btn()
            return "Install option shown in URL Import.", "✓ Nothing was installed automatically."
        if action == "open_assets_folder":
            try:
                subprocess.run(["open", str(ASSETS_DIR)], timeout=5)
                return "Assets folder opened.", "✓ No files were changed."
            except Exception:
                return "Could not open the assets folder automatically.", "Please open the assets folder manually."
        return "No automatic repair is available for this issue.", "Manual review required."

    def _build_single_tab(self, parent):
        PAD = 36

        # ── Select file button ────────────────────────────────────────────────
        self._select_wrap = select_wrap = tk.Frame(parent, bg=BG)
        select_wrap.pack(padx=PAD, fill="x", pady=(22, 0))
        # 1px crimson border via Frame wrapper
        select_border = tk.Frame(select_wrap, bg=CRIMSON, padx=1, pady=1)
        select_border.pack(fill="x")
        self._btn_select = _make_lbtn(
            select_border, "▶   SELECT CASE FILE", self._pick_file,
            bg="#1a1a1a", fg=WHITE, hover_bg="#2a2a2a",
            font=("Helvetica", 13, "bold"), pady=16, padx=22, anchor="w"
        )
        self._btn_select.pack(fill="x")
        tk.Frame(select_wrap, bg=CRIMSON, width=4).place(x=0, y=0, relheight=1.0)

        # ── File card (hidden until chosen) ───────────────────────────────────
        self._card_frame = tk.Frame(parent, bg=BG)
        card_inner = tk.Frame(self._card_frame, bg="#1a1a1a",
                              highlightbackground="#2a2a2a", highlightthickness=1)
        card_inner.pack(fill="x", padx=PAD, pady=(12, 0))
        tk.Frame(card_inner, bg=CRIMSON, height=2).pack(fill="x")
        card_body = tk.Frame(card_inner, bg="#1a1a1a")
        card_body.pack(fill="x", padx=16, pady=12)
        tk.Label(card_body, text="▶", font=("Helvetica", 18, "bold"),
                 fg=CRIMSON, bg="#1a1a1a").grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self._lbl_filename = tk.Label(card_body, text="",
                                      font=("Helvetica", 12, "bold"),
                                      fg=WHITE, bg="#1a1a1a", anchor="w")
        self._lbl_filename.grid(row=0, column=1, sticky="w")
        tk.Label(card_body, text="READY FOR PROCESSING",
                 font=("Helvetica", 8, "bold"), fg=CRIMSON,
                 bg="#1a1a1a", anchor="w").grid(row=1, column=1, sticky="w")
        card_body.columnconfigure(1, weight=1)

        # ── Case Title ────────────────────────────────────────────────────────
        title_frame = tk.Frame(parent, bg=BG)
        title_frame.pack(padx=PAD, fill="x", pady=(16, 0))
        tk.Label(title_frame, text="CASE TITLE", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG).pack(anchor="w")
        self._title_entry = tk.Entry(title_frame, textvariable=tk.StringVar(),
                 font=("Helvetica", 11), fg=WHITE, bg="#1a1a1a",
                 insertbackground=WHITE, relief="flat",
                 highlightthickness=1, highlightbackground="#2a2a2a",
                 highlightcolor=CRIMSON)
        self._title_var = self._title_entry["textvariable"] = tk.StringVar()
        self._title_entry.config(textvariable=self._title_var)
        self._title_entry.pack(fill="x", ipady=8, pady=(6, 0))

        # ── Raw Caption ───────────────────────────────────────────────────────
        caption_frame = tk.Frame(parent, bg=BG)
        caption_frame.pack(padx=PAD, fill="x", pady=(14, 0))
        tk.Label(caption_frame, text="RAW CAPTION", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG).pack(anchor="w")
        self._caption_text = tk.Text(
            caption_frame, height=8, font=("Helvetica", 10),
            fg=WHITE, bg="#1a1a1a", insertbackground=WHITE,
            relief="flat", highlightthickness=1, highlightbackground="#2a2a2a",
            highlightcolor=CRIMSON, wrap="word", padx=8, pady=8
        )
        self._caption_text.pack(fill="x", pady=(6, 0))

        # ── Export button ─────────────────────────────────────────────────────
        export_wrap = tk.Frame(parent, bg=BG)
        export_wrap.pack(padx=PAD, fill="x", pady=(20, 0))
        self._btn_export = _make_lbtn(
            export_wrap, "EXPORT FINISHED REEL", self._start_export,
            bg=MUTED, fg="#888888", hover_bg=CRIMSON_HOT, hover_fg=WHITE,
            normal_fg="#888888", font=("Helvetica", 13, "bold"), pady=16, padx=20
        )
        _lbtn_disable(self._btn_export, MUTED, "#888888")
        self._btn_export.pack(fill="x")

        # ── Case file animation canvas ────────────────────────────────────────
        self._anim_canvas = tk.Canvas(
            parent, bg="#0d0d0d", height=170,
            highlightthickness=1, highlightbackground="#2a2a2a"
        )
        self._anim_canvas.pack(padx=PAD, fill="x", pady=(18, 0))
        self._anim_canvas.bind("<Configure>", lambda e: self._anim_render())

        # Hidden progress/dot/status kept for compat with existing logic
        self._progress = ttk.Progressbar(parent, orient="horizontal", mode="indeterminate")
        self._dot = tk.Label(parent, text="●", fg=BG, bg=BG)
        self._lbl_status = tk.Label(parent, text="", fg=LIGHT_GRAY, bg=BG)

        # Animation state
        self._anim_state   = "idle"   # idle | processing | scheduling | success | error
        self._anim_phase   = 0.0      # 0.0–1.0 within the current state
        self._anim_status  = ""
        self._anim_tick_id = None
        self.after(60, self._anim_render)

        # ── Open folder button ────────────────────────────────────────────────
        self._btn_open = _make_lbtn(
            parent, "▶   OPEN OUTPUT FOLDER", self._open_output_folder,
            bg="#2a2a2a", fg="#AAAAAA", hover_bg="#3a3a3a", hover_fg=WHITE,
            normal_fg="#AAAAAA", font=("Helvetica", 10, "bold"), pady=10, padx=20
        )

    # ── Batch tab ─────────────────────────────────────────────────────────────

    def _build_batch_tab(self, parent):
        PAD = 36

        # ── Quick publish latest ───────────────────────────────────────────────
        quick_border = tk.Frame(parent, bg=CRIMSON, padx=1, pady=1)
        quick_border.pack(padx=PAD, fill="x", pady=(22, 0))
        btn_quick = _make_lbtn(
            quick_border, "⚡   PUBLISH LATEST CASE", self._quick_publish_latest,
            bg="#1a0000", fg=CRIMSON, hover_bg=CRIMSON, hover_fg=WHITE,
            font=("Helvetica", 14, "bold"), pady=18, padx=22, anchor="w"
        )
        btn_quick.pack(fill="x")

        # ── Add videos / DOCX queue buttons ───────────────────────────────────
        add_wrap = tk.Frame(parent, bg=BG)
        add_wrap.pack(padx=PAD, fill="x", pady=(10, 0))
        add_border = tk.Frame(add_wrap, bg=CRIMSON, padx=1, pady=1)
        add_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
        btn_add = _make_lbtn(
            add_border, "▶   ADD VIDEOS", self._batch_add_files,
            bg="#1a1a1a", fg=WHITE, hover_bg="#2a2a2a",
            font=("Helvetica", 13, "bold"), pady=16, padx=22, anchor="w"
        )
        btn_add.pack(fill="x")
        docx_border = tk.Frame(add_wrap, bg="#2a2a2a", padx=1, pady=1)
        docx_border.pack(side="left", fill="x", expand=True)
        btn_docx = _make_lbtn(
            docx_border, "IMPORT DOCX QUEUE", self._batch_import_docx,
            bg="#1a1a1a", fg=WHITE, hover_bg="#2a2a2a",
            font=("Helvetica", 13, "bold"), pady=16, padx=22, anchor="w"
        )
        btn_docx.pack(fill="x")
        tk.Frame(add_wrap, bg=CRIMSON, width=4).place(x=0, y=0, relheight=1.0)

        # ── Column headers ────────────────────────────────────────────────────
        hdr = tk.Frame(parent, bg="#0d0d0d")
        hdr.pack(padx=PAD, fill="x", pady=(12, 0))
        for txt, w in [("SOURCE", 160), ("CASE TITLE", 200), ("DATE", 72), ("", 24)]:
            tk.Label(hdr, text=txt, font=("Helvetica", 7, "bold"),
                     fg="#AAAAAA", bg="#0d0d0d", width=w//7, anchor="w").pack(side="left", padx=6)

        # ── Scrollable list ───────────────────────────────────────────────────
        list_outer = tk.Frame(parent, bg="#0d0d0d",
                              highlightbackground="#2a2a2a", highlightthickness=1)
        list_outer.pack(padx=PAD, fill="both", expand=True, pady=(0, 0))

        self._batch_canvas = tk.Canvas(list_outer, bg="#0d0d0d", highlightthickness=0)
        scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                                 command=self._batch_canvas.yview,
                                 bg="#1a1a1a", troughcolor="#0d0d0d",
                                 activebackground=CRIMSON)
        self._batch_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._batch_canvas.pack(side="left", fill="both", expand=True)

        self._batch_list_frame = tk.Frame(self._batch_canvas, bg="#0d0d0d")
        self._batch_canvas_window = self._batch_canvas.create_window(
            (0, 0), window=self._batch_list_frame, anchor="nw"
        )
        self._batch_list_frame.bind("<Configure>", self._on_batch_list_resize)
        self._batch_canvas.bind("<Configure>", self._on_batch_canvas_resize)

        # Empty state
        self._batch_empty_lbl = tk.Label(
            self._batch_list_frame,
            text="No videos added yet.\nAdd videos or import a DOCX queue to get started.",
            font=("Helvetica", 10), fg="#555555", bg="#0d0d0d", justify="center"
        )
        self._batch_empty_lbl.pack(pady=40)

        # ── Schedule All button ───────────────────────────────────────────────
        sched_wrap = tk.Frame(parent, bg=BG)
        sched_wrap.pack(padx=PAD, fill="x", pady=(14, 0))
        self._btn_schedule_all = _make_lbtn(
            sched_wrap, "SCHEDULE ALL  ( 0 videos )", self._start_batch,
            bg=MUTED, fg="#888888", hover_bg=CRIMSON_HOT, hover_fg=WHITE,
            normal_fg="#888888", font=("Helvetica", 13, "bold"), pady=16, padx=20
        )
        _lbtn_disable(self._btn_schedule_all, MUTED, "#888888")
        self._btn_schedule_all.pack(fill="x")

        # ── Batch status ──────────────────────────────────────────────────────
        status_bar = tk.Frame(parent, bg="#0d0d0d")
        status_bar.pack(padx=PAD, fill="x", pady=(10, 0))
        self._batch_status_lbl = tk.Label(
            status_bar, text="", font=("Courier", 9),
            fg=LIGHT_GRAY, bg="#0d0d0d", wraplength=600, justify="left", anchor="w"
        )
        self._batch_status_lbl.pack(fill="x", padx=12, pady=8)

    def _on_batch_list_resize(self, event):
        self._batch_canvas.configure(scrollregion=self._batch_canvas.bbox("all"))

    def _on_batch_canvas_resize(self, event):
        self._batch_canvas.itemconfig(self._batch_canvas_window, width=event.width)

    # ── Batch row management ──────────────────────────────────────────────────

    def _batch_add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select case videos",
            filetypes=[("Video files", "*.mp4 *.mov"), ("All files", "*.*")]
        )
        for p in paths:
            self._batch_add_row(Path(p))
        self._refresh_batch_ui()

    def _batch_import_docx(self):
        path = filedialog.askopenfilename(
            title="Select DOCX queue",
            filetypes=[("Word document", "*.docx"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            rows = parse_docx_queue(Path(path))
        except Exception as e:
            self._batch_status_lbl.config(
                text=f"Could not read DOCX queue: {e}", fg=ERROR_RED
            )
            return
        if not rows:
            self._batch_status_lbl.config(
                text="No valid rows found. Use a table with URL / Case Title / Caption.",
                fg=ERROR_RED
            )
            return
        for item in rows:
            self._batch_add_row(
                path=None,
                url=item["url"],
                case_title=item["title"],
                caption=item["caption"],
                final_caption=True,
            )
        self._batch_status_lbl.config(
            text=f"Loaded {len(rows)} DOCX queue item{'s' if len(rows) != 1 else ''}.",
            fg="#2d8a4e"
        )
        self._refresh_batch_ui()

    def _quick_publish_latest(self):
        """Auto-import all new cases from the DOCX that aren't yet in Buffer, then publish."""
        if self._batch_running:
            self._batch_status_lbl.config(text="Batch already running.", fg=ERROR_RED)
            return
        if not IMPORT_DOCX_PATH.exists():
            self._batch_status_lbl.config(
                text=f"Not found: {IMPORT_DOCX_PATH.name}", fg=ERROR_RED
            )
            return
        try:
            rows = parse_docx_queue(IMPORT_DOCX_PATH)
        except Exception as e:
            self._batch_status_lbl.config(text=f"Could not read DOCX: {e}", fg=ERROR_RED)
            return
        if not rows:
            self._batch_status_lbl.config(
                text="No valid rows found in the import document.", fg=ERROR_RED
            )
            return

        self._batch_status_lbl.config(text="Checking Buffer queue…", fg=LIGHT_GRAY)
        self.update_idletasks()

        s = load_settings()
        buffer_key = s.get("buffer_key", "").strip()
        channel_id = s.get("buffer_channel_id", "").strip()

        # Find which rows are already scheduled in Buffer by matching the case title
        # against each scheduled post's caption text.
        cutoff_idx = -1  # index of the last row already in Buffer
        if buffer_key and channel_id:
            scheduled_texts, err = fetch_buffer_scheduled_texts(buffer_key, channel_id)
            if err:
                self._batch_status_lbl.config(
                    text=f"Buffer query failed: {err}", fg=ERROR_RED
                )
                return
            if not scheduled_texts:
                self._batch_status_lbl.config(
                    text="Buffer returned no scheduled posts — check API key / channel ID.",
                    fg=ERROR_RED
                )
                return
            combined = "\n".join(t.lower() for t in scheduled_texts)
            for i in range(len(rows) - 1, -1, -1):
                if rows[i]["title"].lower() in combined:
                    cutoff_idx = i
                    break
        else:
            self._batch_status_lbl.config(
                text="Buffer credentials not set in Settings.", fg=ERROR_RED
            )
            return

        new_rows = rows[cutoff_idx + 1:]  # everything after the last synced case

        if not new_rows:
            self._batch_status_lbl.config(
                text="All cases in the document are already scheduled in Buffer.",
                fg="#2d8a4e"
            )
            return

        # Clear existing batch rows
        for row in list(self._batch_rows):
            row["frame"].destroy()
        self._batch_rows.clear()
        self._refresh_batch_ui()

        for item in new_rows:
            self._batch_add_row(
                path=None,
                url=item["url"],
                case_title=item["title"],
                caption=item["caption"],
                final_caption=True,
            )
        self._refresh_batch_ui()

        last_synced = rows[cutoff_idx]["title"] if cutoff_idx >= 0 else "none"
        self._batch_status_lbl.config(
            text=f'Found {len(new_rows)} new case{"s" if len(new_rows) != 1 else ""}'
                 f' after "{last_synced}". Starting…',
            fg=LIGHT_GRAY
        )
        self._start_batch()

    def _batch_add_row(self, path: Path = None, url: str = "",
                       case_title: str = "", caption: str = "",
                       final_caption: bool = False):
        idx = len(self._batch_rows)
        bg = "#111111" if idx % 2 == 0 else "#151515"

        frame = tk.Frame(self._batch_list_frame, bg=bg, pady=0)
        frame.pack(fill="x", padx=0)
        tk.Frame(frame, bg="#2a2a2a", height=1).pack(fill="x")
        inner = tk.Frame(frame, bg=bg)
        inner.pack(fill="x", padx=10, pady=8)

        # Source label (truncated)
        source_name = path.stem if path else re.sub(r"^https?://", "", url)
        fname = source_name[:22] + "…" if len(source_name) > 22 else source_name
        tk.Label(inner, text=fname, font=("Helvetica", 8), fg="#AAAAAA",
                 bg=bg, width=20, anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 8))

        # Case title entry
        initial_title = case_title or (filename_to_display(name_to_filename(path.stem)) if path else "")
        case_var = tk.StringVar(value=initial_title)
        title_entry = tk.Entry(inner, textvariable=case_var,
                               font=("Helvetica", 9), fg=WHITE, bg="#1a1a1a",
                               insertbackground=WHITE, relief="flat",
                               highlightthickness=1, highlightbackground="#2a2a2a",
                               highlightcolor=CRIMSON)
        title_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        # Scheduled date label
        s = load_settings()
        dt = batch_post_datetime(s.get("post_time", "18:00"), idx)
        local_dt = dt.astimezone()
        date_str = local_dt.strftime("%b %-d")
        date_lbl = tk.Label(inner, text=date_str, font=("Helvetica", 8, "bold"),
                            fg=CRIMSON, bg=bg, width=7, anchor="center")
        date_lbl.grid(row=0, column=2, padx=(0, 6))

        # Remove button
        remove_btn = _make_lbtn(
            inner, "✕", lambda i=idx: self._batch_remove_row(i),
            bg=bg, fg="#555555", hover_bg=bg, hover_fg=ERROR_RED, normal_fg="#555555",
            font=("Helvetica", 11, "bold"), pady=2, padx=4
        )
        remove_btn.grid(row=0, column=3, padx=(4, 0))

        # Raw caption text area (full width, row 1)
        caption_text = tk.Text(inner, height=4, font=("Helvetica", 9),
                               fg=WHITE, bg="#1a1a1a", insertbackground=WHITE,
                               relief="flat", highlightthickness=1,
                               highlightbackground="#2a2a2a", highlightcolor=CRIMSON,
                               wrap="word", padx=6, pady=6)
        caption_text.insert("1.0", caption or "Paste raw caption here...")
        caption_text.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 2))

        # Status label (shown after processing)
        status_lbl = tk.Label(inner, text="", font=("Helvetica", 8),
                              fg=LIGHT_GRAY, bg=bg, anchor="w")
        status_lbl.grid(row=2, column=0, columnspan=3, sticky="w")

        inner.columnconfigure(1, weight=1)

        row_data = {
            "path": path,
            "url": url,
            "final_caption": final_caption,
            "case_var": case_var,
            "caption_text": caption_text,
            "frame": frame,
            "status_lbl": status_lbl,
            "date_lbl": date_lbl,
            "idx": idx,
        }
        self._batch_rows.append(row_data)

    def _batch_remove_row(self, original_idx):
        # Find by original idx (rows don't shift their stored idx)
        to_remove = next((r for r in self._batch_rows if r["idx"] == original_idx), None)
        if to_remove:
            to_remove["frame"].destroy()
            self._batch_rows.remove(to_remove)
        self._refresh_batch_ui()
        self._refresh_batch_dates()

    def _refresh_batch_dates(self):
        s = load_settings()
        post_time = s.get("post_time", "18:00")
        for i, row in enumerate(self._batch_rows):
            dt = batch_post_datetime(post_time, i)
            local_dt = dt.astimezone()
            row["date_lbl"].config(text=local_dt.strftime("%b %-d"))

    def _refresh_batch_ui(self):
        n = len(self._batch_rows)
        if n == 0:
            self._batch_empty_lbl.pack(pady=30)
            self._btn_schedule_all.config(text="SCHEDULE ALL  ( 0 videos )")
            _lbtn_disable(self._btn_schedule_all, MUTED, "#888888")
        else:
            self._batch_empty_lbl.pack_forget()
            self._btn_schedule_all.config(
                text=f"SCHEDULE ALL  ( {n} video{'s' if n != 1 else ''} )"
            )
            if not self._batch_running:
                _lbtn_enable(self._btn_schedule_all, CRIMSON, WHITE, CRIMSON_HOT)
            else:
                _lbtn_disable(self._btn_schedule_all, MUTED, "#888888")

    # ── Batch processing ──────────────────────────────────────────────────────

    def _start_batch(self):
        if self._batch_running or not self._batch_rows:
            return
        # Validate all rows have a non-empty case name
        for row in self._batch_rows:
            if not row["case_var"].get().strip():
                self._batch_status_lbl.config(
                    text="⚠  All videos need a case title.", fg=CRIMSON
                )
                return
            if not row.get("path") and not row.get("url"):
                self._batch_status_lbl.config(
                    text="⚠  Each batch row needs a video file or URL.", fg=CRIMSON
                )
                return
        if any(row.get("url") for row in self._batch_rows):
            try:
                r = subprocess.run(ytdlp_cmd(["--version"]), capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    raise FileNotFoundError
            except Exception:
                self._batch_status_lbl.config(
                    text="⚠  yt-dlp is needed for DOCX URL batches. Open URL Import and install yt-dlp.",
                    fg=CRIMSON
                )
                return
        self._batch_running = True
        _lbtn_disable(self._btn_schedule_all, MUTED, "#888888")
        self._batch_status_lbl.config(text="🔴  Processing batch...", fg=LIGHT_GRAY)
        threading.Thread(target=self._run_batch, daemon=True).start()

    def _run_batch(self):
        s = load_settings()
        has_buffer = bool(s.get("buffer_key") and s.get("buffer_channel_id"))
        post_time = s.get("post_time", "18:00")
        rows = list(self._batch_rows)  # snapshot

        # Query Buffer once: first video lands one day after the last scheduled
        # post; each subsequent video is one more day after that.
        base_due = None
        if has_buffer:
            base_due = next_available_date_safe(
                s["buffer_key"], s["buffer_channel_id"], post_time, limit_s=10.0
            )

        for i, row in enumerate(rows):
            raw_name = row["case_var"].get().strip()
            title    = name_to_filename(raw_name)
            raw_caption = row["caption_text"].get("1.0", "end").strip()
            path     = row.get("path")
            source_url = row.get("url", "")
            log_lines = []

            def set_row_status(msg, color=LIGHT_GRAY, row=row):
                self.after(0, lambda: row["status_lbl"].config(text=msg, fg=color))

            def set_batch_status(msg, color=LIGHT_GRAY):
                self.after(0, lambda: self._batch_status_lbl.config(text=msg, fg=color))

            # Per-row scheduled slot = base + i days at post_time
            due_dt = _date_at_post_time(
                base_due + datetime.timedelta(days=i), post_time
            ) if base_due else batch_post_datetime(post_time, i)
            row_local = due_dt.astimezone()
            row_date  = row_local.strftime("%b %-d, %Y")
            row_time  = row_local.strftime("%-I:%M %p")

            if source_url and not path:
                set_row_status(f"⏳  Downloading… ({i+1}/{len(rows)})")
            else:
                set_row_status(f"⏳  Exporting… ({i+1}/{len(rows)})")
            set_batch_status(
                f"🔴  Processing {i+1}/{len(rows)}: {raw_name}  ·  📅 {row_date} at {row_time}"
            )

            # Step 1: download URL rows, then run ffmpeg pipeline
            try:
                if source_url and not path:
                    download_dir = Path(__file__).parent / "_docx_downloads" / f"{int(time.time())}-{i}"
                    path = download_video_url(source_url, download_dir, s, log_lines)
                    set_row_status(f"⏳  Exporting… ({i+1}/{len(rows)})")
                output_path = run_export_pipeline(
                    path, title, log_lines,
                    status_cb=lambda msg, rw=row: self.after(
                        0, lambda m=msg, r=rw: r["status_lbl"].config(text=m)
                    )
                )
            except Exception as e:
                set_row_status(f"✗  Export failed: {e}", ERROR_RED)
                continue  # move to next video

            if not has_buffer:
                self._library_save_case(title, output_path, status="Ready")
                set_row_status(f"✓  Saved as {output_path.name}", "#2d8a4e")
                continue

            # Step 2: caption. DOCX captions are final Buffer captions.
            caption = raw_caption if row.get("final_caption") else reformat_caption(title, raw_caption)

            # Step 3: upload
            set_row_status("📤  Uploading…")
            try:
                video_url = upload_video(output_path)
            except Exception as e:
                set_row_status(f"✓  Saved  ·  Upload failed: {e}", ERROR_RED)
                continue

            set_row_status("⏳  Waiting for Archive.org…")
            archive_ready = wait_for_public_video_url(
                video_url,
                status_cb=lambda msg, rw=row: self.after(
                    0, lambda m=msg, r=rw: r["status_lbl"].config(text=m, fg=LIGHT_GRAY)
                ),
                log_lines=log_lines,
                max_attempts=8,
            )
            if not archive_ready:
                self._library_save_case(
                    title, output_path, status="Uploaded",
                    archive_url=video_url, caption=caption,
                    scheduled_date="", buffer_post_id=""
                )
                set_row_status(
                    "✓  Uploaded · Archive.org still processing. Try Schedule All again later.",
                    ERROR_RED
                )
                continue

            # Step 4: schedule using the per-row slot computed above
            try:
                data = {}
                raw_text = ""
                last_msg = ""
                for buf_attempt in range(1, 6):
                    raw_text, result = schedule_to_buffer(
                        caption, video_url,
                        s["buffer_channel_id"], s["buffer_key"],
                        post_time,
                        due_at_dt=due_dt
                    )
                    log_lines.append(f"Buffer attempt {buf_attempt}: {raw_text[:500]}")
                    data = result.get("data", {}).get("createPost", {})
                    if "post" in data:
                        break
                    last_msg = data.get("message", "unexpected response")
                    if buffer_video_not_ready(last_msg) and buf_attempt < 5:
                        wait_s = 30 * buf_attempt
                        set_row_status(
                            f"⏳  Archive.org still processing — retrying Buffer in {wait_s}s "
                            f"({buf_attempt}/5)"
                        )
                        time.sleep(wait_s)
                        continue
                    break
                if "post" in data:
                    due     = data["post"].get("dueAt", "")
                    post_id = data["post"].get("id", "")
                    try:
                        dt = datetime.datetime.fromisoformat(due.replace("Z", "+00:00"))
                        local_dt = dt.astimezone()
                        due_fmt = local_dt.strftime("%b %-d at %-I:%M %p")
                    except Exception:
                        due_fmt = due
                    _s = load_settings(); _s["last_scheduled_date"] = due; save_settings(_s)
                    self._library_save_case(title, output_path, status="Scheduled",
                                            archive_url=video_url, caption=caption,
                                            scheduled_date=due, buffer_post_id=post_id)
                    set_row_status(f"✅  Scheduled for {due_fmt}", "#2d8a4e")
                elif "message" in data:
                    set_row_status(f"✓  Saved  ·  Buffer: {data['message']}", ERROR_RED)
                else:
                    set_row_status(f"✓  Saved  ·  Buffer: {last_msg or 'unexpected response'}", ERROR_RED)
            except Exception as e:
                set_row_status(f"✓  Saved  ·  Buffer failed: {e}", ERROR_RED)

        # Done
        self._batch_running = False
        self.after(0, lambda: self._batch_status_lbl.config(
            text=f"✅  Batch complete — {len(rows)} video{'s' if len(rows)!=1 else ''} processed.",
            fg="#2d8a4e"
        ))
        self.after(0, self._refresh_batch_ui)

    # ── URL Import tab ────────────────────────────────────────────────────────

    def _build_url_tab(self, parent):
        PAD = 30
        scroll_outer = tk.Frame(parent, bg=BG)
        scroll_outer.pack(fill="both", expand=True)
        canvas_scroll = tk.Canvas(scroll_outer, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_outer, orient="vertical",
                                  command=canvas_scroll.yview)
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas_scroll.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas_scroll, bg=BG)
        inner_win = canvas_scroll.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(e):
            canvas_scroll.itemconfig(inner_win, width=e.width)
        def _on_inner_configure(e):
            canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        canvas_scroll.bind("<Configure>", _on_resize)
        inner.bind("<Configure>", _on_inner_configure)

        # ── Ollama status bar ─────────────────────────────────────────────────
        ollama_bar = tk.Frame(inner, bg="#111111",
                              highlightthickness=1, highlightbackground="#2a2a2a")
        ollama_bar.pack(fill="x", padx=PAD, pady=(18, 0))
        ollama_inner = tk.Frame(ollama_bar, bg="#111111")
        ollama_inner.pack(fill="x", padx=12, pady=8)
        self._ollama_dot = tk.Label(ollama_inner, text="●", bg="#111111",
                                    fg="#444444", font=("Helvetica", 10))
        self._ollama_dot.pack(side="left")
        self._ollama_status_lbl = tk.Label(
            ollama_inner, text="Checking Ollama...", bg="#111111",
            fg=LIGHT_GRAY, font=("Helvetica", 10)
        )
        self._ollama_status_lbl.pack(side="left", padx=(6, 0))
        self._btn_install_ollama = _make_lbtn(
            ollama_inner, "Install Ollama", self._url_install_ollama,
            bg="#1a1a1a", fg=LIGHT_GRAY, hover_bg="#2a2a2a",
            font=("Helvetica", 9), pady=4, padx=10
        )
        # packed/hidden dynamically by _url_check_ollama_status

        # ── URL input ─────────────────────────────────────────────────────────
        tk.Label(inner, text="PASTE VIDEO URL", bg=BG, fg=LIGHT_GRAY,
                 font=("Helvetica", 10, "bold")).pack(anchor="w", padx=PAD, pady=(18, 4))
        url_frame = tk.Frame(inner, bg="#1a1a1a",
                             highlightthickness=1, highlightbackground="#333333")
        url_frame.pack(fill="x", padx=PAD)
        self._url_entry = tk.Entry(url_frame, bg="#1a1a1a", fg=WHITE, insertbackground=WHITE,
                                   font=("Courier", 13), bd=0, relief="flat",
                                   highlightthickness=0)
        self._url_entry.pack(fill="x", padx=10, pady=10)
        self._url_entry.insert(0, "https://")
        self._url_entry.bind("<FocusIn>", self._url_entry_focus)

        # ── Platform buttons (cosmetic) ───────────────────────────────────────
        plat_frame = tk.Frame(inner, bg=BG)
        plat_frame.pack(padx=PAD, pady=(10, 0), anchor="w")
        self._url_plat_btns = {}
        for plat in ("TikTok", "Instagram", "YouTube"):
            btn = tk.Label(plat_frame, text=plat, bg="#1a1a1a", fg="#555555",
                           font=("Helvetica", 10, "bold"), padx=14, pady=6,
                           cursor="hand2", highlightthickness=0)
            btn.pack(side="left", padx=(0, 6))
            self._url_plat_btns[plat] = btn
        self._url_entry.bind("<KeyRelease>", lambda e: self._url_detect_platform())

        # ── Case title ────────────────────────────────────────────────────────
        title_row = tk.Frame(inner, bg=BG)
        title_row.pack(fill="x", padx=PAD, pady=(18, 4))
        tk.Label(title_row, text="CASE TITLE", bg=BG, fg=LIGHT_GRAY,
                 font=("Helvetica", 10, "bold")).pack(side="left")
        self._url_ai_badge = tk.Label(title_row, text="  ✦ AI will auto-detect",
                                      bg=BG, fg="#444444", font=("Helvetica", 9))
        self._url_ai_badge.pack(side="left", padx=(8, 0))
        title_frame = tk.Frame(inner, bg="#1a1a1a",
                               highlightthickness=1, highlightbackground="#333333")
        title_frame.pack(fill="x", padx=PAD)
        self._url_title_entry = tk.Entry(title_frame, bg="#1a1a1a", fg=WHITE,
                                         insertbackground=WHITE, font=("Helvetica", 13),
                                         bd=0, relief="flat", highlightthickness=0)
        self._url_title_entry.pack(fill="x", padx=10, pady=10)

        # ── Buffer caption ────────────────────────────────────────────────────
        cap_row = tk.Frame(inner, bg=BG)
        cap_row.pack(fill="x", padx=PAD, pady=(18, 4))
        tk.Label(cap_row, text="BUFFER CAPTION", bg=BG, fg=LIGHT_GRAY,
                 font=("Helvetica", 10, "bold")).pack(side="left")
        self._url_cap_badge = tk.Label(cap_row, text="  ✦ AI will generate",
                                       bg=BG, fg="#444444", font=("Helvetica", 9))
        self._url_cap_badge.pack(side="left", padx=(8, 0))
        cap_frame = tk.Frame(inner, bg="#1a1a1a",
                             highlightthickness=1, highlightbackground="#333333")
        cap_frame.pack(fill="x", padx=PAD)
        self._url_caption_text = tk.Text(cap_frame, bg="#1a1a1a", fg=WHITE,
                                         insertbackground=WHITE, font=("Helvetica", 12),
                                         bd=0, relief="flat", highlightthickness=0,
                                         wrap="word", height=7)
        self._url_caption_text.pack(fill="x", padx=10, pady=10)

        self._btn_use_my_caption = _make_lbtn(
            inner, "USE THIS CAPTION", self._start_url_use_my_caption,
            bg="#1a1a1a", fg=LIGHT_GRAY, hover_bg="#2a2a2a", hover_fg=WHITE,
            font=("Helvetica", 10, "bold"), pady=9, padx=16
        )
        self._btn_use_my_caption.pack(padx=PAD, fill="x", pady=(8, 0))

        # ── Import & Schedule button ──────────────────────────────────────────
        btn_wrapper = tk.Frame(inner, bg=CRIMSON, padx=2, pady=2)
        btn_wrapper.pack(padx=PAD, pady=(20, 0), fill="x")
        self._btn_url_import = _make_lbtn(
            btn_wrapper, "IMPORT & SCHEDULE", self._start_url_import,
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 14, "bold"), pady=16
        )
        self._btn_url_import.pack(fill="x")

        # ── Animation canvas ──────────────────────────────────────────────────
        self._url_anim_canvas = tk.Canvas(
            inner, bg="#0d0d0d", height=170,
            highlightthickness=1, highlightbackground="#2a2a2a"
        )
        self._url_anim_canvas.pack(padx=PAD, fill="x", pady=(18, 20))
        self._url_anim_canvas.bind("<Configure>", lambda e: self._url_anim_render())

        self._url_anim_state   = "idle"
        self._url_anim_phase   = 0.0
        self._url_anim_status  = ""
        self._url_anim_tick_id = None
        self.after(60, self._url_anim_render)

        # ── Retry & Schedule button (hidden until Archive.org poll exhausted) ──
        self._btn_retry_schedule = _make_lbtn(
            inner, "↻  RETRY & SCHEDULE", self._url_retry_schedule,
            bg="#1a4a1a", fg="#2d8a4e", hover_bg="#2a5a2a", hover_fg=WHITE,
            font=("Helvetica", 12, "bold"), pady=12
        )
        # Packed/hidden dynamically — stays hidden until UploadPendingError

        # Check Ollama status after UI is built
        self.after(200, self._url_check_ollama_status)

    def _url_entry_focus(self, e):
        if self._url_entry.get() == "https://":
            self._url_entry.delete(0, "end")

    def _url_detect_platform(self):
        url = self._url_entry.get().lower()
        detected = None
        if "tiktok.com" in url:
            detected = "TikTok"
        elif "instagram.com" in url:
            detected = "Instagram"
        elif "youtube.com" in url or "youtu.be" in url:
            detected = "YouTube"
        for plat, btn in self._url_plat_btns.items():
            if plat == detected:
                btn.config(bg=CRIMSON, fg=WHITE)
            else:
                btn.config(bg="#1a1a1a", fg="#555555")

    def _url_prepare_next_import(self):
        self._url_entry.delete(0, "end")
        self._url_entry.insert(0, "https://")
        self._url_title_entry.delete(0, "end")
        self._url_caption_text.delete("1.0", "end")
        self._pending_upload_url = None
        self._pending_caption = None
        self._pending_due_dt = None
        if hasattr(self, "_btn_retry_schedule") and self._btn_retry_schedule.winfo_exists():
            self._btn_retry_schedule.pack_forget()
        self._url_detect_platform()
        self._url_entry.focus_set()
        self._url_entry.selection_range(0, "end")

    def _check_model_installed(self):
        """Check on startup if the configured AI model is installed; show banner if not."""
        def _check():
            model = get_ai_model("caption")
            installed = check_ollama_model_installed(model)
            if not installed:
                self.after(0, lambda: self._show_model_banner(model))
        threading.Thread(target=_check, daemon=True).start()

    def _show_model_banner(self, model: str):
        if hasattr(self, "_model_banner") and self._model_banner.winfo_exists():
            return
        self._model_banner = tk.Frame(self._outer, bg="#1a0a00",
                                      highlightthickness=1, highlightbackground=CRIMSON)
        self._model_banner.pack(fill="x", padx=30, pady=(8, 0), before=self._single_frame)
        inner = tk.Frame(self._model_banner, bg="#1a0a00")
        inner.pack(fill="x", padx=12, pady=8)
        tk.Label(inner, text=f"⚠  Recommended AI model ({model}) is not installed.",
                 bg="#1a0a00", fg="#ffaa44",
                 font=("Helvetica", 10)).pack(side="left")
        _make_lbtn(inner, "Install Model",
                   lambda: self._install_ai_model(model),
                   bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
                   font=("Helvetica", 9, "bold"), pady=4, padx=12).pack(side="right")

    def _install_ai_model(self, model: str):
        win = tk.Toplevel(self, bg=BG)
        win.title(f"Installing {model}")
        win.geometry("620x340")
        win.resizable(False, False)
        tk.Label(win, text=f"INSTALLING {model.upper()}", bg=BG, fg=WHITE,
                 font=("Helvetica", 13, "bold")).pack(pady=(20, 6))
        tk.Label(win, text="This may take several minutes — do not close this window.",
                 bg=BG, fg=LIGHT_GRAY, font=("Helvetica", 10)).pack()
        log_frame = tk.Frame(win, bg="#0d0d0d", highlightthickness=1,
                             highlightbackground="#333333")
        log_frame.pack(fill="both", expand=True, padx=20, pady=14)
        log_txt = tk.Text(log_frame, bg="#0d0d0d", fg=LIGHT_GRAY, font=("Courier", 9),
                          bd=0, wrap="word", state="disabled", highlightthickness=0)
        log_txt.pack(fill="both", expand=True, padx=8, pady=8)
        done_lbl = tk.Label(win, text="", bg=BG, fg="#2d8a4e",
                            font=("Helvetica", 11, "bold"))
        done_lbl.pack(pady=(0, 14))

        def _append(line):
            log_txt.config(state="normal")
            log_txt.insert("end", line + "\n")
            log_txt.see("end")
            log_txt.config(state="disabled")

        def _run():
            try:
                self.after(0, lambda: _append(f"→ Pulling {model}..."))
                ollama_bin = shutil.which("ollama") or "/usr/local/bin/ollama"
                proc = subprocess.Popen(
                    [ollama_bin, "pull", model],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                for line in proc.stdout:
                    self.after(0, lambda l=line.rstrip(): _append(l))
                proc.wait()
                if proc.returncode == 0:
                    self.after(0, lambda: done_lbl.config(
                        text=f"✅  {model} is ready!", fg="#2d8a4e"))
                    if hasattr(self, "_model_banner") and self._model_banner.winfo_exists():
                        self.after(0, self._model_banner.destroy)
                else:
                    self.after(0, lambda: done_lbl.config(
                        text=f"✗  Pull failed — run: ollama pull {model}", fg=ERROR_RED))
            except Exception as e:
                self.after(0, lambda: done_lbl.config(text=f"✗  Error: {e}", fg=ERROR_RED))

        threading.Thread(target=_run, daemon=True).start()

    def _url_check_ollama_status(self):
        def _check():
            ok = check_ollama()
            self.after(0, lambda: self._url_apply_ollama_status(ok))
        threading.Thread(target=_check, daemon=True).start()

    def _url_apply_ollama_status(self, ok: bool):
        model = get_ai_model("caption")
        speed_mode = get_ai_speed_mode()
        if ok:
            self._ollama_dot.config(fg="#2d8a4e")
            self._ollama_status_lbl.config(
                text=f"Ollama ready — {speed_mode} mode ({model})", fg="#2d8a4e"
            )
            self._btn_install_ollama.pack_forget()
            self._url_ai_badge.config(fg="#2d8a4e")
            self._url_cap_badge.config(fg="#2d8a4e")
        else:
            self._ollama_dot.config(fg=ERROR_RED)
            self._ollama_status_lbl.config(
                text=f"Ollama not running or {model} not installed — captions must be entered manually",
                fg=LIGHT_GRAY
            )
            self._btn_install_ollama.pack(side="left", padx=(10, 0))
            self._url_ai_badge.config(fg="#444444")
            self._url_cap_badge.config(fg="#444444")

    def _url_install_ollama(self):
        """Open a top-level progress window and run Ollama install + model pull."""
        win = tk.Toplevel(self, bg=BG)
        win.title("Installing Ollama")
        win.geometry("620x380")
        win.resizable(False, False)
        tk.Label(win, text="INSTALLING OLLAMA", bg=BG, fg=WHITE,
                 font=("Helvetica", 13, "bold")).pack(pady=(20, 6))
        tk.Label(win, text="This may take a few minutes — do not close this window.",
                 bg=BG, fg=LIGHT_GRAY, font=("Helvetica", 10)).pack()
        log_frame = tk.Frame(win, bg="#0d0d0d",
                             highlightthickness=1, highlightbackground="#333333")
        log_frame.pack(fill="both", expand=True, padx=20, pady=14)
        log_txt = tk.Text(log_frame, bg="#0d0d0d", fg=LIGHT_GRAY,
                          font=("Courier", 9), bd=0, wrap="word",
                          state="disabled", highlightthickness=0)
        log_txt.pack(fill="both", expand=True, padx=8, pady=8)
        done_lbl = tk.Label(win, text="", bg=BG, fg="#2d8a4e",
                            font=("Helvetica", 11, "bold"))
        done_lbl.pack(pady=(0, 14))

        def _append(line):
            log_txt.config(state="normal")
            log_txt.insert("end", line + "\n")
            log_txt.see("end")
            log_txt.config(state="disabled")

        def _run():
            try:
                # Step 1: install Ollama — needs admin rights on macOS.
                # osascript's "with administrator privileges" shows the native
                # macOS password dialog so we never need a terminal sudo.
                self.after(0, lambda: _append(
                    "→ Downloading Ollama (macOS password dialog will appear)..."
                ))
                install_script = (
                    "curl -fsSL https://ollama.com/install.sh -o /tmp/_ollama_install.sh && "
                    "bash /tmp/_ollama_install.sh"
                )
                osa_cmd = [
                    "osascript", "-e",
                    f'do shell script "{install_script}" with administrator privileges'
                ]
                proc = subprocess.run(osa_cmd, capture_output=True, text=True, timeout=300)
                if proc.stdout:
                    for line in proc.stdout.splitlines():
                        self.after(0, lambda l=line: _append(l))
                if proc.stderr:
                    for line in proc.stderr.splitlines():
                        self.after(0, lambda l=line: _append(l))
                if proc.returncode != 0:
                    self.after(0, lambda: done_lbl.config(
                        text="✗  Install failed — check the log above.", fg=ERROR_RED))
                    return
                self.after(0, lambda: _append("✓  Ollama installed."))

                # Step 2: pull the identify model plus the selected caption model.
                ollama_bin = "/usr/local/bin/ollama"
                models_to_pull = []
                for m in (get_ai_model("identify"), get_ai_model("caption")):
                    if m not in models_to_pull:
                        models_to_pull.append(m)
                for model_name in models_to_pull:
                    self.after(0, lambda m=model_name: _append(
                        f"\n→ Pulling {m} model (this may take a few minutes)..."
                    ))
                    proc2 = subprocess.Popen(
                        [ollama_bin, "pull", model_name],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                    )
                    for line in proc2.stdout:
                        self.after(0, lambda l=line.rstrip(): _append(l))
                    proc2.wait()
                    if proc2.returncode != 0:
                        self.after(0, lambda m=model_name: done_lbl.config(
                            text=f"✗  Model pull failed — try: ollama pull {m}",
                            fg=ERROR_RED))
                        return

                self.after(0, lambda: done_lbl.config(
                    text="✅  Ollama installed and AI models ready!", fg="#2d8a4e"))
                self.after(0, self._url_check_ollama_status)
            except Exception as e:
                self.after(0, lambda: done_lbl.config(
                    text=f"✗  Error: {e}", fg=ERROR_RED))

        threading.Thread(target=_run, daemon=True).start()

    def _url_set_status(self, text, error=False):
        self._url_anim_status = text
        if error:
            self._url_anim_enter("error")
        elif not text:
            self._url_anim_enter("idle")
        elif "✅" in text or "Scheduled for" in text:
            self._url_anim_enter("success")
        elif "Buffer" in text or "Scheduling" in text:
            self._url_anim_enter("scheduling")
        elif text:
            if self._url_anim_state not in ("processing", "scheduling", "success"):
                self._url_anim_enter("processing")
        self._url_anim_render()

    def _url_anim_enter(self, state):
        if state == self._url_anim_state and state not in ("success",):
            return
        if self._url_anim_tick_id:
            self.after_cancel(self._url_anim_tick_id)
            self._url_anim_tick_id = None
        self._url_anim_state = state
        self._url_anim_phase = 0.0
        if state in ("processing", "scheduling"):
            self._url_anim_tick()
        elif state == "success":
            self._url_anim_success_tick()

    def _url_anim_tick(self):
        if self._url_anim_state not in ("processing", "scheduling"):
            return
        self._url_anim_phase = (self._url_anim_phase + 0.018) % 1.0
        self._url_anim_render()
        self._url_anim_tick_id = self.after(40, self._url_anim_tick)

    def _url_anim_success_tick(self):
        self._url_anim_phase += 0.04
        self._url_anim_render()
        if self._url_anim_phase < 1.0:
            self._url_anim_tick_id = self.after(16, self._url_anim_success_tick)

    def _start_url_import(self):
        print("[URL IMPORT] Button clicked")
        url = self._url_entry.get().strip()
        title = self._url_title_entry.get().strip()
        raw_caption = self._url_caption_text.get("1.0", "end").strip()
        print(f"[URL IMPORT] url={url!r}  title={title!r}  caption_len={len(raw_caption)}")

        if not url or url == "https://":
            print("[URL IMPORT] BLOCKED: empty URL")
            self._url_set_status("Paste a video URL to import.", error=True)
            return

        # Check yt-dlp synchronously (fast — just --version)
        print("[URL IMPORT] Checking yt-dlp...")
        try:
            r = subprocess.run(ytdlp_cmd(["--version"]), capture_output=True, text=True, timeout=10)
            print(f"[URL IMPORT] yt-dlp check returncode={r.returncode} stdout={r.stdout.strip()}")
            if r.returncode != 0:
                raise FileNotFoundError
        except FileNotFoundError:
            print("[URL IMPORT] BLOCKED: yt-dlp not found")
            self._url_set_status(
                "yt-dlp is not installed. Run: pip install yt-dlp", error=True
            )
            self._url_show_install_btn()
            return
        except subprocess.TimeoutExpired:
            print("[URL IMPORT] BLOCKED: yt-dlp --version timed out")
            self._url_set_status("yt-dlp check timed out — try again.", error=True)
            return

        # Disable button and hand off to background thread.
        # check_ollama() has a 3-second network timeout — run it on the thread,
        # NOT here on the main thread where it would freeze the UI.
        print("[URL IMPORT] Handing off to background thread")
        _lbtn_disable(self._btn_url_import, MUTED, "#888888")
        _lbtn_disable(self._btn_use_my_caption, "#1a1a1a", "#555555")
        self._url_set_status("⏳  Fetching video metadata...")
        threading.Thread(
            target=self._run_url_import,
            args=(url, title, raw_caption),
            daemon=True
        ).start()

    def _start_url_use_my_caption(self):
        raw_caption = self._url_caption_text.get("1.0", "end").strip()
        if not raw_caption:
            self._url_set_status("Paste the Buffer caption first.", error=True)
            return
        self._start_url_import()

    def _url_show_install_btn(self):
        if hasattr(self, "_url_install_btn") and self._url_install_btn.winfo_exists():
            return
        self._url_install_btn = _make_lbtn(
            self._url_anim_canvas.master, "Install yt-dlp",
            self._url_install_ytdlp,
            bg="#1a1a1a", fg=LIGHT_GRAY, hover_bg="#2a2a2a",
            font=("Helvetica", 10), pady=8, padx=16
        )
        self._url_install_btn.pack(pady=(0, 8))

    def _url_install_ytdlp(self):
        self._url_set_status("⏳  Installing yt-dlp...")
        def _install():
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "yt-dlp"],
                    capture_output=True, text=True, timeout=120
                )
                r = subprocess.run(ytdlp_cmd(["--version"]), capture_output=True, text=True)
                if r.returncode == 0:
                    self.after(0, lambda: self._url_set_status(
                        "yt-dlp installed! Paste a URL and click Import."
                    ))
                    if hasattr(self, "_url_install_btn") and self._url_install_btn.winfo_exists():
                        self.after(0, self._url_install_btn.pack_forget)
                else:
                    self.after(0, lambda: self._url_set_status(
                        "Install failed — run: pip install yt-dlp", error=True
                    ))
            except Exception as e:
                self.after(0, lambda: self._url_set_status(f"Install error: {e}", error=True))
        threading.Thread(target=_install, daemon=True).start()

    def _url_retry_schedule(self):
        """Re-check Archive.org URL and schedule to Buffer when confirmed HTTP 200."""
        if not self._pending_upload_url:
            return
        self._btn_retry_schedule.pack_forget()
        _lbtn_disable(self._btn_url_import, MUTED, "#888888")
        url      = self._pending_upload_url
        caption  = self._pending_caption
        due_dt   = self._pending_due_dt
        s        = load_settings()
        bkey     = s.get("buffer_key", "")
        bcid     = s.get("buffer_channel_id", "")
        post_time = s.get("post_time", "18:00")

        def _check():
            self.after(0, lambda: self._url_set_status("⏳  Checking Archive.org..."))
            check = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "-L", "--max-time", "15", url],
                capture_output=True, text=True
            )
            http_code = check.stdout.strip()
            print(f"[{_ts()} URL_IMPORT] Retry check: HTTP {http_code}")
            if http_code != "200":
                self.after(0, lambda: self._url_set_status(
                    "Archive.org is still processing. Try again in a few minutes.", error=True))
                self.after(0, lambda: self._btn_retry_schedule.pack(padx=30, pady=(0, 8), fill="x"))
                self.after(0, lambda: _lbtn_enable(
                    self._btn_url_import, CRIMSON, WHITE, CRIMSON_HOT))
                return
            # Ready — schedule
            self.after(0, lambda: self._url_set_status("⏳  Scheduling to Buffer..."))
            try:
                _due = due_dt or next_available_date_safe(bkey, bcid, post_time, limit_s=10.0)
                raw_text, result_b = schedule_to_buffer(
                    caption, url, bcid, bkey, post_time, due_at_dt=_due
                )
                data = result_b.get("data", {}).get("createPost", {})
                if "post" in data:
                    due = data["post"].get("dueAt", "")
                    try:
                        dt = datetime.datetime.fromisoformat(due.replace("Z", "+00:00"))
                        local_dt = dt.astimezone()
                        due_fmt  = local_dt.strftime("%b %-d at %-I:%M %p")
                    except Exception:
                        due_fmt = due
                    _sv = load_settings(); _sv["last_scheduled_date"] = due; save_settings(_sv)
                    self.after(0, lambda f=due_fmt: self._url_set_status(f"✅  Scheduled for {f}!"))
                    self.after(0, self._url_prepare_next_import)
                else:
                    msg = data.get("message", "unexpected response")
                    self.after(0, lambda m=msg: self._url_set_status(f"Buffer error: {m}", error=True))
            except Exception as e:
                self.after(0, lambda: self._url_set_status(
                    f"Buffer failed — check your API key in Settings.", error=True))
                print(f"[{_ts()} URL_IMPORT] Retry schedule exception: {e}")
            finally:
                self.after(0, lambda: _lbtn_enable(
                    self._btn_url_import, CRIMSON, WHITE, CRIMSON_HOT))

        threading.Thread(target=_check, daemon=True).start()

    def _run_url_import(self, url: str, title: str, raw_caption: str):
        import traceback, tempfile, glob
        print(f"[URL IMPORT] Thread started — url={url!r}")
        log_lines = []
        output_path = None
        tmpdir = None

        s = load_settings()
        bkey = s.get("buffer_key", "")
        bcid = s.get("buffer_channel_id", "")
        post_time = s.get("post_time", "18:00")
        has_buffer = bool(bkey and bcid)

        # Check Ollama here on the background thread (has a 3s timeout — safe)
        print("[URL IMPORT] Checking Ollama...")
        identify_model_ok = check_ollama_model_installed(get_ai_model("identify"))
        ollama_ok = True
        print(f"[URL IMPORT] identify_model_ok={identify_model_ok}")

        def _st(msg, err=False):
            print(f"[URL IMPORT] status: {msg}")
            self.after(0, lambda m=msg, e=err: self._url_set_status(m, e))

        def _re_enable():
            print("[URL IMPORT] Re-enabling button")
            self.after(0, lambda: _lbtn_enable(self._btn_url_import, CRIMSON, WHITE, CRIMSON_HOT))
            self.after(0, lambda: _lbtn_enable(
                self._btn_use_my_caption, "#1a1a1a", LIGHT_GRAY, "#2a2a2a"
            ))

        try:
            # ── Step 1: fetch metadata with yt-dlp --dump-json ────────────────
            print("[URL IMPORT] Step 1: fetching metadata")
            _st("⏳  Fetching video metadata...")

            preferred = s.get("preferred_browser", "chrome")
            fallbacks = [b for b in ("chrome", "safari", "firefox") if b != preferred]
            browser_order = [preferred] + fallbacks + [None]

            def _ytdlp_run(base_args, timeout=30):
                """Try yt-dlp with preferred browser first, then fallbacks, then no cookies.
                Returns (result, browser_used) where browser_used may be None."""
                for browser in browser_order:
                    cookie_args = ["--cookies-from-browser", browser] if browser else []
                    cmd = ytdlp_cmd(cookie_args + base_args)
                    print(f"[{_ts()} URL_IMPORT] yt-dlp cmd (browser={browser}): {cmd[:8]}...")
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                    print(f"[{_ts()} URL_IMPORT] returncode={r.returncode} browser={browser}")
                    if r.returncode != 0 and browser is not None:
                        print(f"[{_ts()} URL_IMPORT] warning: browser={browser} failed — {r.stderr[:150]}")
                    if r.returncode == 0:
                        return r, browser
                # All attempts failed — return last result so caller can inspect stderr
                return r, None

            # Kick off Ollama warmup ping in parallel with the metadata fetch
            # so the model is hot by the time we need it for case identification.
            _warmup_done = threading.Event()
            _ai_model = get_ai_model("caption")
            def _ollama_warmup():
                if check_ollama_model_installed(_ai_model):
                    try:
                        import urllib.request as _ur
                        _payload = json.dumps({
                            "model": _ai_model, "prompt": "hi",
                            "stream": False, "options": {"num_predict": 1, "think": False}
                        }).encode()
                        _req = _ur.Request(
                            "http://localhost:11434/api/generate", data=_payload,
                            headers={"Content-Type": "application/json"}
                        )
                        _ur.urlopen(_req, timeout=30)
                        print(f"[{_ts()} URL_IMPORT] Ollama warmup complete ({_ai_model})")
                    except Exception as e:
                        print(f"[{_ts()} URL_IMPORT] Ollama warmup skipped: {e}")
                _warmup_done.set()
            threading.Thread(target=_ollama_warmup, daemon=True).start()

            meta_result, meta_browser = _ytdlp_run(
                ["--dump-json", "--no-playlist", url], timeout=30
            )
            print(f"[URL IMPORT] metadata returncode={meta_result.returncode} browser={meta_browser}")
            meta = {}
            if meta_result.returncode == 0 and meta_result.stdout.strip():
                try:
                    meta = json.loads(meta_result.stdout)
                except Exception as parse_err:
                    print(f"[URL IMPORT] metadata JSON parse failed: {parse_err}")

            # Wait for warmup to finish (usually already done by the time metadata arrives)
            _warmup_done.wait(timeout=35)
            vid_title, uploader, full_text, tags = parse_ytdlp_metadata(meta)
            print(f"[URL IMPORT] ALL meta keys: {list(meta.keys())}")
            print(f"[URL IMPORT] Title: {vid_title!r}")
            print(f"[URL IMPORT] Full text: {full_text[:300]!r}")
            print(f"[URL IMPORT] Tags: {tags[:200]!r}")
            log_lines.append(
                f"Metadata: title={vid_title!r} uploader={uploader!r} "
                f"desc_len={len(full_text)} tags={tags[:100]!r}"
            )

            t_step_start = time.time()

            # ── Step 2: Identify case name ────────────────────────────────────
            # Fast deterministic fallback — extract plausible proper names from
            # the caption. Used before/after Ollama so common captions avoid delay.
            def _regex_case_name(text: str) -> str:
                snippet = text[:1600]
                name_word = r'[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿß]{1,}'
                name_pat = rf'{name_word}\s+{name_word}(?:\s+{name_word})?'
                # Instagram often exposes strong subject clues as CamelCase tags.
                for tag in re.findall(r'#([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9]{3,})', snippet):
                    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', tag).strip()
                    if len(spaced.split()) >= 2:
                        return spaced

                # Common true-crime structure: "At 101 years old, Josef Schütz became..."
                age_intro = re.search(
                    rf'\bAt\s+\d+\s+years?\s+old,\s+({name_pat})\s+'
                    r'(?:was|is|became|remains|served|stood)\b',
                    snippet
                )
                if age_intro:
                    return age_intro.group(1)

                # Prefer explicit biography-style sentences: "Otto Warmbier was..."
                bio_match = re.search(
                    rf'\b({name_pat})\s+'
                    r'(?:was|is|remains|became)\b',
                    snippet
                )
                if bio_match:
                    return bio_match.group(1)

                # Match sequences of Title-Case words (2+ words, each 2+ chars)
                matches = re.findall(
                    rf'\b({name_pat})\b', snippet
                )
                # Filter out common non-name phrases and date openers.
                skip = {
                    "True Crime", "Breaking News", "Cold Case", "Serial Killer",
                    "This Video", "The Story", "What Happened", "Video By",
                    "On July", "On January", "On February", "On March", "On April",
                    "On May", "On June", "On August", "On September", "On October",
                    "On November", "On December",
                    "North Korea", "South Korea", "United States", "United Kingdom",
                    "Afghanistan Yemen", "Yemen Syria",
                }
                bad_first_words = {"On", "In", "At", "By", "The", "This", "Video"}
                bad_last_words = {"Jr", "Sr", "Junior", "Senior"}
                for m in matches:
                    words = m.split()
                    if (
                        m not in skip
                        and words[0] not in bad_first_words
                        and words[-1] not in bad_last_words
                        and len(words) <= 4
                        and len(m) > 4
                    ):
                        return m
                return ""

            if ollama_ok:
                # If the user already typed a case title, skip AI identification entirely
                if title:
                    detected_case = title
                    confidence    = 1.0
                    timed_out     = False
                    log_lines.append(f"[{_ts()}] Identify: skipped — user provided title {title!r}")
                    print(f"[{_ts()} URL_IMPORT] Identify: skipped (user title present)")
                else:
                    t_identify_start = time.time()
                    quick_name = _regex_case_name(full_text) or _regex_case_name(vid_title)
                    if quick_name:
                        detected_case = quick_name
                        confidence = 0.8
                        timed_out = False
                        log_lines.append(f"[{_ts()}] Fast name extract: {detected_case!r}")
                        print(f"[{_ts()} URL_IMPORT] Fast name extract: {detected_case!r}")
                    else:
                        _st("⏳  Identifying case with AI...")
                    # Use fast model (llama3.1:8b) — identify is a simple name-extraction task
                        identify_prompt = (
                            f"Read this text and tell me the name of the criminal case or person it is about.\n\n"
                            f"Text: {full_text[:500]}\n\n"
                            "Reply with ONLY the person's name or case name. Nothing else. One line only.\n"
                            'Example: "Joseph Kallinger" or "Cassie Jo Stoddart"\n\n'
                            "If truly unknown reply: UNKNOWN"
                        )
                        detected_case = "UNKNOWN"
                        confidence = 0.0
                        timed_out = False
                        try:
                            raw_response = ollama_identify(identify_prompt).strip()
                            print(f"[{_ts()} URL_IMPORT] Identify raw: {raw_response[:200]!r}")
                            first_line = next(
                                (l.strip() for l in raw_response.splitlines() if l.strip()), ""
                            )
                            if first_line and len(first_line) <= 80 and first_line.upper() != "UNKNOWN":
                                detected_case = first_line
                                confidence = 0.85
                            log_lines.append(f"[{_ts()}] Identify: {detected_case!r} conf={confidence:.2f}")
                        except Exception as e:
                            timed_out = True
                            log_lines.append(f"[{_ts()}] Ollama identify failed/timed out: {e}")
                            print(f"[{_ts()} URL_IMPORT] Identify exception (timeout?): {e}")

                        # Regex fallback when Ollama times out or returns nothing
                        if timed_out or detected_case == "UNKNOWN":
                            regex_name = _regex_case_name(full_text) or _regex_case_name(vid_title)
                            if regex_name:
                                detected_case = regex_name
                                confidence    = 0.8
                                log_lines.append(f"[{_ts()}] Regex fallback name: {detected_case!r}")
                                print(f"[{_ts()} URL_IMPORT] Regex fallback: {detected_case!r}")

                    t_identify_ms = int((time.time() - t_identify_start) * 1000)
                    print(f"[{_ts()} URL_IMPORT] Identify took {t_identify_ms}ms (timed_out={timed_out})")

                # If confidence < 0.75, show confirmation dialog before continuing
                if confidence < 0.75 or detected_case.upper() == "UNKNOWN" or not detected_case:
                    confirm_done  = threading.Event()
                    confirmed_name = [title or ""]   # pre-fill with user-supplied or empty

                    def _show_confirm_dialog():
                        dlg = tk.Toplevel(self, bg=BG)
                        dlg.title("Confirm Case Name")
                        dlg.geometry("500x220")
                        dlg.resizable(False, False)
                        dlg.grab_set()
                        dlg.update_idletasks()
                        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
                        dlg.geometry(f"500x220+{(sw-500)//2}+{(sh-220)//2}")

                        if timed_out:
                            header_txt = "AI IDENTIFY TIMED OUT"
                            hint = (
                                f"Ollama timed out. Regex extracted: {detected_case!r}\n"
                                "Please confirm or correct the case name:"
                            )
                        else:
                            header_txt = "AI CONFIDENCE LOW"
                            hint = (
                                f"AI detected: {detected_case!r}  (confidence: {confidence:.0%})\n"
                                "Please confirm or correct the case name:"
                            )
                        tk.Label(dlg, text=header_txt, bg=BG, fg=CRIMSON,
                                 font=("Helvetica", 12, "bold")).pack(pady=(18, 4))
                        del header_txt
                        tk.Label(dlg, text=hint, bg=BG, fg=LIGHT_GRAY,
                                 font=("Helvetica", 10)).pack(pady=(0, 10))

                        name_frame = tk.Frame(dlg, bg="#1a1a1a",
                                             highlightthickness=1, highlightbackground="#333333")
                        name_frame.pack(fill="x", padx=24)
                        name_entry = tk.Entry(name_frame, bg="#1a1a1a", fg=WHITE,
                                              insertbackground=WHITE, font=("Helvetica", 13),
                                              bd=0, relief="flat", highlightthickness=0)
                        name_entry.pack(fill="x", padx=10, pady=10)
                        name_entry.insert(0, detected_case if detected_case != "UNKNOWN" else (title or ""))

                        def _ok():
                            confirmed_name[0] = name_entry.get().strip()
                            dlg.destroy()
                            confirm_done.set()
                        def _cancel():
                            confirmed_name[0] = None
                            dlg.destroy()
                            confirm_done.set()

                        btn_row = tk.Frame(dlg, bg=BG)
                        btn_row.pack(fill="x", padx=24, pady=(10, 0))
                        _make_lbtn(btn_row, "CONTINUE", _ok, bg=CRIMSON, fg=WHITE,
                                   hover_bg=CRIMSON_HOT, font=("Helvetica", 11, "bold"),
                                   pady=10).pack(side="left", fill="x", expand=True, padx=(0, 6))
                        _make_lbtn(btn_row, "CANCEL", _cancel, bg="#2a2a2a", fg=WHITE,
                                   hover_bg="#3a3a3a", font=("Helvetica", 11, "bold"),
                                   pady=10).pack(side="left", fill="x", expand=True)
                        dlg.protocol("WM_DELETE_WINDOW", _cancel)
                        dlg.wait_window()

                    self.after(0, _show_confirm_dialog)
                    confirm_done.wait()

                    if confirmed_name[0] is None:
                        _re_enable(); _st(""); return
                    if confirmed_name[0]:
                        detected_case = confirmed_name[0]

                if not title:
                    if detected_case and detected_case.upper() != "UNKNOWN":
                        self.after(0, lambda t=detected_case: (
                            self._url_title_entry.delete(0, "end"),
                            self._url_title_entry.insert(0, t)
                        ))
                        title = detected_case
                    else:
                        self.after(0, lambda: self._url_set_status(
                            "Could not identify case — please enter a title manually.", error=True
                        ))
                        _re_enable(); return
                # User-supplied title always wins

                # ── Step 3: tiered source lookup ──────────────────────────────
                wiki_facts = ""
                wiki_title = ""
                verification_sources = []
                source_prompt_text = ""
                blocked_prompt_text = "None."
                verified_fact_sheet = ""
                confidence_label = "Very low"
                confidence_reason = "Only the original video caption or weak context is available."
                source_section = source_section_for_caption([])
                if not raw_caption:
                    t_src_start = time.time()

                    # Wikipedia first — its wikitext contains curated citation URLs
                    # (BBC, AP, Reuters, .gov press releases) that we use as sources.
                    # Fetching it before gather_verification_sources means we only
                    # ever call gather_verification_sources once.
                    _st("⏳  Checking encyclopedia and sources...")
                    t_wiki_start = time.time()
                    wiki_facts, wiki_title = fetch_wikipedia_summary(title)
                    t_wiki_ms = int((time.time() - t_wiki_start) * 1000)
                    if wiki_facts:
                        log_lines.append(
                            f"[{_ts()}] Wikipedia orientation: {wiki_title} "
                            f"({len(wiki_facts)} chars, {t_wiki_ms}ms)"
                        )
                    else:
                        log_lines.append(f"[{_ts()}] Encyclopedia: not found")

                    _st("⏳  Searching official and reporting sources...")
                    verification_sources = gather_verification_sources(
                        title, full_text, wiki_title, wiki_facts
                    )

                    source_prompt_text = format_sources_for_prompt(verification_sources)
                    blocked_prompt_text = format_blocked_sources_for_prompt(verification_sources)
                    confidence_label, confidence_reason = verification_confidence(verification_sources)
                    verified_fact_sheet = build_verified_fact_sheet(title, verification_sources)
                    log_lines.append(
                        f"[{_ts()}] Sources found: {len(verification_sources)} "
                        f"({int((time.time() - t_src_start) * 1000)}ms)"
                    )
                    log_lines.append(
                        f"[{_ts()}] Verification confidence: {confidence_label} — {confidence_reason}"
                    )
                    for src in verification_sources:
                        log_lines.append(f"Source: {src.get('title')} — {src.get('url')}")
                    source_section = source_section_for_caption(verification_sources)
                    if verification_sources and any(s.get("tier") != "Wikipedia" for s in verification_sources):
                        _st(f"⏳  Found {len(verification_sources)} source(s)")
                    elif wiki_facts:
                        _st("⏳  No independent sources — using Wikipedia orientation")
                    else:
                        _st("⚠  No sources or encyclopedia found — using video caption cautiously")

                    if confidence_label == "Very low":
                        log_lines.append(
                            f"[{_ts()}] Caption generation stopped: research confidence too low"
                        )
                        stop_done = threading.Event()

                        def _show_research_stop_dialog():
                            dlg = tk.Toplevel(self, bg=BG)
                            dlg.title("RESEARCH NEEDED — VERDICTIN60")
                            dlg.geometry("620x330")
                            dlg.resizable(False, False)
                            dlg.grab_set()
                            dlg.update_idletasks()
                            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
                            dlg.geometry(f"620x330+{(sw-620)//2}+{(sh-330)//2}")

                            tk.Label(
                                dlg,
                                text="RESEARCH CONFIDENCE TOO LOW",
                                bg=BG, fg=CRIMSON,
                                font=("Helvetica", 14, "bold")
                            ).pack(pady=(22, 8))
                            tk.Label(
                                dlg,
                                text=(
                                    "The app could not find enough accessible official records "
                                    "or reputable reporting to verify this case to the VerdictIn60 standard."
                                ),
                                bg=BG, fg=OFF_WHITE,
                                font=("Helvetica", 11),
                                wraplength=540,
                                justify="center"
                            ).pack(pady=(0, 12))
                            tk.Label(
                                dlg,
                                text=(
                                    "No caption was generated or sent to review. "
                                    "You can paste a caption you have already checked into BUFFER CAPTION "
                                    "and use that, or try this link again later."
                                ),
                                bg=BG, fg=LIGHT_GRAY,
                                font=("Helvetica", 10),
                                wraplength=540,
                                justify="center"
                            ).pack(pady=(0, 18))

                            def _close():
                                dlg.destroy()
                                stop_done.set()

                            _make_lbtn(
                                dlg, "OK", _close,
                                bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
                                font=("Helvetica", 11, "bold"), pady=10
                            ).pack(fill="x", padx=190)
                            dlg.protocol("WM_DELETE_WINDOW", _close)
                            dlg.wait_window()

                        self.after(0, _show_research_stop_dialog)
                        stop_done.wait()
                        _st("Research confidence too low — no caption generated.")
                        _re_enable()
                        return

                # ── Step 3b: Ollama — generate grounded caption ───────────────
                if not raw_caption:
                    caption_model = get_ai_model("caption")
                    if not check_ollama_model_installed(caption_model):
                        log_lines.append(f"[{_ts()}] Caption model missing: {caption_model}")
                        generated_caption = fallback_verdict_caption(
                            title, full_text, source_section,
                            cautious=confidence_label in ("Low", "Very low")
                        )
                        _st(f"⚠  {caption_model} not available — using original caption fallback.")
                        raw_caption = generated_caption
                        self.after(0, lambda cap=generated_caption: (
                            self._url_caption_text.delete("1.0", "end"),
                            self._url_caption_text.insert("1.0", cap)
                        ))
                    else:
                        _st(f"⏳  Generating caption with AI ({caption_model})...")
                        t_gen_start = time.time()
                        if source_prompt_text and len(source_prompt_text) >= 1000:
                            caption_prompt = (
                                "You are writing a VerdictIn60 Instagram caption.\n\n"
                                f"Primary subject: {title}\n"
                                f"Verification confidence: {confidence_label} — {confidence_reason}\n\n"
                                "Use only the verified fact sheet and accessible sources below. "
                                "Do not invent names, dates, motives, quotes, locations, charges, sentences, or emotional details. "
                                "If a detail is not supported, omit it or phrase cautiously.\n\n"
                                "Verified fact sheet:\n"
                                f"{verified_fact_sheet}\n\n"
                                "Accessible sources:\n"
                                f"{source_prompt_text[:6500]}\n\n"
                                "Blocked but discovered sources:\n"
                                f"{blocked_prompt_text[:1800]}\n\n"
                                "Requirements:\n"
                                "- Strong hook, short dramatic paragraphs, chronological storytelling.\n"
                                "- Clear respectful tone; no unsupported dramatic claims.\n"
                                "- Add one engagement question near the end.\n"
                                f"- Include this subtle creator credit near the end if it fits naturally: {creator_credit_line(uploader) or 'Original video via the original creator.'}\n"
                                "- Include: Follow @VerdictIn60 for daily true crime.\n"
                                "- End with this exact Research & Verification section:\n"
                                f"{source_section}\n"
                                "- Include exactly 20 relevant hashtags at the end.\n"
                                "- Do not list Wikipedia in Research & Verification.\n"
                                "- End the entire answer with END_OF_CAPTION.\n"
                                "- Return only the caption."
                            )
                        else:
                            verified_block = source_prompt_text[:1200] if source_prompt_text else "No independent source found."
                            caption_prompt = (
                                "You are writing a VerdictIn60 Instagram caption.\n\n"
                                f"Primary subject: {title}\n"
                                f"Verification confidence: {confidence_label} — {confidence_reason}\n\n"
                                "Use accessible sources first. The video caption is unverified context; use it carefully. "
                                "Do not invent facts. If verification is weak, write cautiously.\n\n"
                                "Verified fact sheet:\n"
                                f"{verified_fact_sheet}\n\n"
                                "Accessible sources:\n"
                                f"{verified_block}\n\n"
                                "Blocked but discovered sources:\n"
                                f"{blocked_prompt_text[:1200]}\n\n"
                                "Unverified video caption context:\n"
                                f"{full_text[:1200]}\n\n"
                                "Requirements:\n"
                                "- Strong hook, short dramatic paragraphs, chronological storytelling.\n"
                                "- Clear respectful tone; no unsupported dramatic claims.\n"
                                "- Add one engagement question near the end.\n"
                                f"- Include this subtle creator credit near the end if it fits naturally: {creator_credit_line(uploader) or 'Original video via the original creator.'}\n"
                                "- Include: Follow @VerdictIn60 for daily true crime.\n"
                                "- End with this exact Research & Verification section:\n"
                                f"{source_section}\n"
                                "- Include exactly 20 relevant hashtags at the end.\n"
                                "- Do not list Wikipedia in Research & Verification.\n"
                                "- End the entire answer with END_OF_CAPTION.\n"
                                "- Return only the caption."
                            )
                        generated_caption = ""
                        _ollama_raw_response = ""
                        try:
                            _ollama_raw_response = ollama_generate(caption_prompt, task="caption")
                            generated_caption = _ollama_raw_response.strip()
                            t_gen_ms = int((time.time() - t_gen_start) * 1000)
                            log_lines.append(
                                f"[{_ts()}] Caption generated with {caption_model} "
                                f"({len(generated_caption)} chars, {t_gen_ms}ms)"
                            )
                        except Exception as e:
                            log_lines.append(f"[{_ts()}] Ollama caption exception: {e}")
                            log_lines.append(f"[{_ts()}] Ollama raw response: {_ollama_raw_response!r}")
                            print(f"[{_ts()} URL_IMPORT] Caption generation exception: {e}")
                            print(f"[{_ts()} URL_IMPORT] Raw response: {_ollama_raw_response!r}")
                            generated_caption = fallback_verdict_caption(
                                title, full_text, source_section,
                                cautious=confidence_label in ("Low", "Very low")
                            )
                            log_lines.append(
                                f"[{_ts()}] Caption fallback used after AI failure "
                                f"({len(generated_caption)} chars)"
                            )
                            if is_timeout_error(e):
                                _st("⚠  AI timed out — using original caption fallback.")
                            else:
                                _st("⚠  AI caption failed — using original caption fallback.")

                        # Strip thinking blocks before any further processing
                        if generated_caption:
                            generated_caption = re.sub(
                                r'<think>.*?</think>', '', generated_caption,
                                flags=re.DOTALL | re.IGNORECASE
                            ).strip()

                        if not generated_caption:
                            log_lines.append(f"[{_ts()}] Caption generation returned empty. Raw: {_ollama_raw_response!r}")
                            print(f"[{_ts()} URL_IMPORT] Empty caption — aborting. Raw: {_ollama_raw_response!r}")
                            generated_caption = fallback_verdict_caption(
                                title, full_text, source_section,
                                cautious=confidence_label in ("Low", "Very low")
                            )
                            log_lines.append(
                                f"[{_ts()}] Caption fallback used after empty AI response "
                                f"({len(generated_caption)} chars)"
                            )
                            _st("⚠  AI returned nothing — using original caption fallback.")
                        else:
                            missing_end_marker = "END_OF_CAPTION" not in generated_caption
                            if missing_end_marker:
                                log_lines.append(
                                    f"[{_ts()}] Caption fallback used because AI output missed END_OF_CAPTION "
                                    f"({len(generated_caption)} chars)"
                                )
                                print(f"[{_ts()} URL_IMPORT] AI caption rejected: missing END_OF_CAPTION")
                                generated_caption = fallback_verdict_caption(
                                    title, full_text, source_section,
                                    cautious=confidence_label in ("Low", "Very low")
                                )
                                _st("⚠  AI caption was incomplete — using original caption fallback.")
                            else:
                                generated_caption = generated_caption.replace("END_OF_CAPTION", "").strip()

                        if generated_caption:
                            # Diagnostic: show the tail of the AI output so we can see
                            # exactly what the unfinished-sentence check is looking at
                            tail = generated_caption[-200:]
                            print(f"[{_ts()} URL_IMPORT] Caption tail (last 200 chars): {tail!r}")
                            log_lines.append(f"[{_ts()}] Caption tail: {tail!r}")
                            fallback_reason = caption_needs_fallback(generated_caption)
                            if fallback_reason:
                                log_lines.append(
                                    f"[{_ts()}] Caption fallback used because AI output was {fallback_reason} "
                                    f"({len(generated_caption)} chars)"
                                )
                                print(
                                    f"[{_ts()} URL_IMPORT] AI caption rejected: {fallback_reason}"
                                )
                                generated_caption = fallback_verdict_caption(
                                    title, full_text, source_section,
                                    cautious=confidence_label in ("Low", "Very low")
                                )
                                _st(f"⚠  AI caption was {fallback_reason} — using original caption fallback.")

                        raw_caption = generated_caption
                        self.after(0, lambda cap=generated_caption: (
                            self._url_caption_text.delete("1.0", "end"),
                            self._url_caption_text.insert("1.0", cap)
                        ))

                # Always give subtle credit to the original reel creator when
                # the uploader handle is available from the imported URL.
                credited_caption = ensure_creator_credit(raw_caption, uploader)
                if credited_caption != raw_caption:
                    raw_caption = credited_caption
                    log_lines.append(
                        f"[{_ts()}] Added original creator credit: "
                        f"{creator_credit_line(uploader)!r}"
                    )
                    self.after(0, lambda cap=credited_caption: (
                        self._url_caption_text.delete("1.0", "end"),
                        self._url_caption_text.insert("1.0", cap)
                    ))

                # ── Step 3c: AI verification pass ─────────────────────────────
                hallucination_warnings = []
                real_sources = [
                    s for s in verification_sources
                    if s.get("kind") not in ("Orientation only",)
                    and s.get("tier") != "Wikipedia"
                ]
                has_verifiable_sources = len(real_sources) >= 2
                has_official_source = any(
                    s.get("kind") == "Official"
                    for s in real_sources
                )
                if real_sources and len(real_sources) < 2:
                    log_lines.append(
                        f"[{_ts()}] AI verification skipped: only "
                        f"{len(real_sources)} independent source found"
                    )
                elif real_sources and not has_official_source:
                    log_lines.append(
                        f"[{_ts()}] AI verification running without official source"
                    )
                has_any_source = any(
                    s.get("kind") not in ("Orientation only",)
                    for s in verification_sources
                )
                if (
                    raw_caption and has_verifiable_sources
                    and check_ollama_model_installed(get_ai_model("verify"))
                ):
                    _st("⏳  Verifying caption facts with AI...")
                    t_verify_start = time.time()
                    source_mode = (
                        "thin_verified_source" if len(source_prompt_text or wiki_facts) < 1500
                        else "verified_source"
                    )
                    verify_prompt = (
                        "Fact-check this true crime caption. Be strict but fair.\n\n"
                        "Independent source material:\n"
                        f"{(source_prompt_text or wiki_facts)[:7000]}\n\n"
                        "Unverified video caption context:\n"
                        f"{full_text[:1200]}\n\n"
                        "Caption:\n"
                        f"{raw_caption}\n\n"
                        "Rules:\n"
                        "- hallucinations = claims found in neither independent source material nor video context.\n"
                        "- warnings = claims found only in unverified video caption context.\n"
                        "- Critical facts need two independent sources when possible.\n"
                        "- Names, dates, locations, verdicts, sentences, appeals, cause of death, and current status should preferably include an official source.\n"
                        "- If independent source material is thin, do not call video-context claims hallucinations; warn instead.\n"
                        "Return only valid JSON:\n"
                        '{"approved": true, "confidence": 0.9, '
                        '"hallucinations": ["list any invented facts"], '
                        '"warnings": ["list any unsupported claims"]}'
                    )
                    try:
                        verify_raw = ollama_generate(
                            verify_prompt, task="verify", timeout=45, num_predict=220
                        ).strip()
                        print(f"[{_ts()} URL_IMPORT] Verify raw: {verify_raw[:400]!r}")
                        json_m = re.search(r'\{.*\}', verify_raw, re.DOTALL)
                        if json_m:
                            vresult = json.loads(json_m.group())
                            v_approved     = vresult.get("approved", True)
                            v_confidence   = float(vresult.get("confidence", 0.9))
                            v_hallucinations = vresult.get("hallucinations", [])
                            v_warnings     = vresult.get("warnings", [])
                            t_verify_ms = int((time.time() - t_verify_start) * 1000)
                            if source_mode == "thin_verified_source" and v_hallucinations:
                                v_warnings = v_warnings + [
                                    f"Needs manual source check: {h}"
                                    for h in v_hallucinations
                                ]
                                v_hallucinations = []
                                v_approved = True
                                v_confidence = min(v_confidence, 0.75)
                            log_lines.append(
                                f"[{_ts()}] Verify: approved={v_approved} conf={v_confidence:.2f} "
                                f"hallucinations={v_hallucinations} ({t_verify_ms}ms)"
                            )
                            print(
                                f"[{_ts()} URL_IMPORT] Verify result: approved={v_approved} "
                                f"conf={v_confidence:.2f} hallucinations={v_hallucinations}"
                            )
                            # Auto-approve if confident and clean
                            if v_approved and v_confidence > 0.9 and not v_hallucinations:
                                log_lines.append(f"[{_ts()}] Auto-approved — no hallucinations detected")
                            else:
                                hallucination_warnings = v_hallucinations + v_warnings
                        else:
                            hallucination_warnings.append(
                                "AI verification did not return a usable result; review the sources manually."
                            )
                            log_lines.append(f"[{_ts()}] Verify returned invalid JSON: {verify_raw[:300]!r}")
                    except Exception as e:
                        print(f"[{_ts()} URL_IMPORT] Verify exception: {e}")
                        log_lines.append(f"[{_ts()}] Verify failed: {e}")

                # ── Step 3d: Review & Approve dialog ─────────────────────────
                # Block this background thread until the user approves or cancels.
                approved_caption = [None]   # mutable container for result across threads
                dialog_done = threading.Event()
                if not verification_sources:
                    hallucination_warnings.insert(
                        0,
                        "No independent sources were found; this caption is based mainly on the video caption."
                    )
                else:
                    non_reference = [
                        s for s in verification_sources
                        if s.get("kind") != "Orientation only"
                        and s.get("tier") != "Wikipedia"
                        and not s.get("blocked")
                    ]
                    official = [s for s in non_reference if s.get("kind") == "Official"]
                    if confidence_label in ("Low", "Very low"):
                        hallucination_warnings.insert(
                            0,
                            f"Verification confidence is {confidence_label.lower()}: {confidence_reason}"
                        )
                    if len(non_reference) < 2:
                        hallucination_warnings.insert(
                            0,
                            "Fewer than two independent sources were found; review claims carefully before scheduling."
                        )
                    if not official:
                        hallucination_warnings.insert(
                            0,
                            "No official source was found; critical facts should be checked against primary records."
                        )
                _warnings_snap = list(hallucination_warnings)  # snapshot for closure

                def _show_review_dialog():
                    case_for_display = title
                    cap_for_display  = raw_caption or ""

                    dlg = tk.Toplevel(self, bg=BG)
                    dlg.title("REVIEW — VERDICTIN60")
                    dlg.geometry("700x660")
                    dlg.resizable(False, False)
                    dlg.grab_set()

                    # Center on screen
                    dlg.update_idletasks()
                    sw = dlg.winfo_screenwidth()
                    sh = dlg.winfo_screenheight()
                    dlg.geometry(f"700x660+{(sw-700)//2}+{(sh-660)//2}")

                    # Header
                    tk.Label(dlg, text="REVIEW BEFORE SCHEDULING",
                             bg=BG, fg=LIGHT_GRAY,
                             font=("Helvetica", 10, "bold")).pack(pady=(18, 4))
                    tk.Label(dlg, text=f"✓  Case: {case_for_display}",
                             bg=BG, fg=CRIMSON,
                             font=("Helvetica", 13, "bold")).pack(pady=(0, 6))

                    # Hallucination warnings (shown in red if any)
                    if _warnings_snap:
                        warn_frame = tk.Frame(dlg, bg="#1a0000",
                                             highlightthickness=1, highlightbackground="#660000")
                        warn_frame.pack(fill="x", padx=24, pady=(0, 8))
                        tk.Label(warn_frame,
                                 text="⚠  AI FACT-CHECK WARNINGS — Review carefully:",
                                 bg="#1a0000", fg=ERROR_RED,
                                 font=("Helvetica", 9, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
                        for w in _warnings_snap[:6]:
                            tk.Label(warn_frame, text=f"  • {w}", bg="#1a0000",
                                     fg="#ff8888", font=("Helvetica", 9),
                                     wraplength=620, justify="left").pack(anchor="w", padx=8)
                        tk.Frame(warn_frame, bg="#1a0000", height=6).pack()

                    if verification_sources:
                        src_frame = tk.Frame(dlg, bg="#101010",
                                             highlightthickness=1, highlightbackground="#333333")
                        src_frame.pack(fill="x", padx=24, pady=(0, 8))
                        tk.Label(src_frame, text=f"SOURCES FOUND — CONFIDENCE: {confidence_label.upper()}",
                                 bg="#101010", fg=LIGHT_GRAY,
                                 font=("Helvetica", 9, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
                        for src in verification_sources[:5]:
                            status = "blocked" if src.get("blocked") else src.get("kind", "Source")
                            tk.Label(
                                src_frame,
                                text=f"• [{status}] {src.get('title','Source')} — {src.get('url','')}",
                                bg="#101010", fg="#AAAAAA",
                                font=("Helvetica", 8),
                                wraplength=620, justify="left"
                            ).pack(anchor="w", padx=8)
                        tk.Frame(src_frame, bg="#101010", height=6).pack()

                    tk.Frame(dlg, bg="#2a2a2a", height=1).pack(fill="x", padx=24)

                    # Editable caption text area
                    cap_frame = tk.Frame(dlg, bg="#1a1a1a",
                                        highlightthickness=1, highlightbackground="#333333")
                    cap_frame.pack(fill="both", expand=True, padx=24, pady=14)
                    cap_txt = tk.Text(cap_frame, bg="#1a1a1a", fg=WHITE,
                                     insertbackground=WHITE, font=("Helvetica", 12),
                                     bd=0, relief="flat", highlightthickness=0,
                                     wrap="word", height=20)
                    cap_txt.pack(fill="both", expand=True, padx=8, pady=8)
                    cap_txt.insert("1.0", cap_for_display)

                    # Empty-caption warning label (hidden until needed)
                    empty_warn = tk.Label(dlg, text="⚠  Caption cannot be empty.",
                                         bg=BG, fg=ERROR_RED,
                                         font=("Helvetica", 10, "bold"))

                    # Buttons
                    btn_row = tk.Frame(dlg, bg=BG)
                    btn_row.pack(fill="x", padx=24, pady=(0, 18))

                    approve_wrap = tk.Frame(btn_row, bg=CRIMSON, padx=2, pady=2)
                    approve_wrap.pack(side="left", fill="x", expand=True, padx=(0, 6))
                    approve_btn = _make_lbtn(
                        approve_wrap, "✓  APPROVE & SCHEDULE", lambda: None,
                        bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
                        font=("Helvetica", 12, "bold"), pady=14
                    )
                    approve_btn.pack(fill="x")

                    def _approve():
                        text = cap_txt.get("1.0", "end").strip()
                        if not text:
                            empty_warn.pack(before=btn_row, pady=(0, 6))
                            return
                        empty_warn.pack_forget()
                        approved_caption[0] = text
                        dlg.destroy()
                        dialog_done.set()

                    approve_btn._lbtn_command = _approve
                    approve_btn.bind("<Button-1>", lambda e: _approve() if not approve_btn._lbtn_disabled else None)

                    def _cancel():
                        approved_caption[0] = None
                        dlg.destroy()
                        dialog_done.set()

                    cancel_wrap = tk.Frame(btn_row, bg="#444444", padx=1, pady=1)
                    cancel_wrap.pack(side="left", fill="x", expand=True, padx=(6, 0))
                    _make_lbtn(cancel_wrap, "✗  CANCEL", _cancel,
                               bg="#2a2a2a", fg=WHITE, hover_bg="#3a3a3a",
                               font=("Helvetica", 12, "bold"), pady=14).pack(fill="x")

                    dlg.protocol("WM_DELETE_WINDOW", _cancel)
                    dlg.wait_window()

                self.after(0, _show_review_dialog)
                dialog_done.wait()   # background thread blocks here

                if approved_caption[0] is None:
                    print("[URL IMPORT] User cancelled at review dialog")
                    _re_enable()
                    _st("")
                    return

                raw_caption = approved_caption[0]
                print(f"[URL IMPORT] Approved caption ({len(raw_caption)} chars)")
                _st("⏳  Starting download...")

            # ── Step 4: compute Buffer slot ───────────────────────────────────
            print(f"[URL IMPORT] Step 4: Buffer slot  has_buffer={has_buffer}")
            due_dt = None
            if has_buffer:
                _st("⏳  Checking schedule...")
                due_dt = next_available_date_safe(bkey, bcid, post_time, limit_s=10.0)
                local_due = due_dt.astimezone()
                date_str = local_due.strftime("%b %-d, %Y")
                time_str = local_due.strftime("%-I:%M %p")
                log_lines.append(f"Next slot: {due_dt.isoformat()}")
                _st(f"📅  Scheduling for {date_str} at {time_str}")

            # ── Step 5: download with yt-dlp ──────────────────────────────────
            print("[URL IMPORT] Step 5: starting download")
            _st("⏳  Downloading video...")
            tmpdir = tempfile.mkdtemp()
            output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            dl_result, dl_browser = _ytdlp_run([
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", output_template,
                "--no-playlist",
                url
            ], timeout=180)
            log_lines.append(f"yt-dlp stdout: {dl_result.stdout[-800:]}")
            log_lines.append(f"yt-dlp stderr: {dl_result.stderr[-400:]}")
            if dl_result.returncode != 0:
                stderr_lower = dl_result.stderr.lower()
                if any(w in stderr_lower for w in ("login", "log in", "cookie", "auth", "403", "private")):
                    raise RuntimeError(
                        "Instagram requires browser login to download. "
                        "Make sure you are logged into Instagram in Safari or Chrome, then try again."
                    )
                raise RuntimeError(
                    f"yt-dlp failed (code {dl_result.returncode}): {dl_result.stderr[-300:]}"
                )

            print(f"[URL IMPORT] yt-dlp download ok, browser={dl_browser}")
            mp4_files = glob.glob(os.path.join(tmpdir, "*.mp4"))
            if not mp4_files:
                raise RuntimeError("yt-dlp finished but no .mp4 file found in temp directory.")
            src_path = Path(mp4_files[0])
            print(f"[URL IMPORT] Downloaded: {src_path.name}")
            log_lines.append(f"Downloaded: {src_path.name}")

            # ── Step 6: normalise to exact 1080×1920 30fps H.264 ─────────────
            # The CTA concat filter requires every segment to match exactly.
            # We normalise whenever codec is not h264 OR dimensions are not 1080×1920.
            print("[URL IMPORT] Step 6: probing downloaded video format")
            _st("⏳  Checking video format...")
            probe_r = subprocess.run(
                [FFPROBE, "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(src_path)],
                capture_output=True, text=True
            )
            needs_normalise = True   # default: normalise unless probe proves unnecessary
            try:
                pdata = json.loads(probe_r.stdout)
                vstreams = [s for s in pdata.get("streams", []) if s.get("codec_type") == "video"]
                astreams = [s for s in pdata.get("streams", []) if s.get("codec_type") == "audio"]
                if vstreams:
                    vc  = vstreams[0].get("codec_name", "")
                    w   = int(vstreams[0].get("width", 0))
                    h   = int(vstreams[0].get("height", 0))
                    ac  = astreams[0].get("codec_name", "") if astreams else ""
                    needs_normalise = not (
                        vc == "h264" and w == 1080 and h == 1920
                        and ac in ("aac", "mp3", "")
                    )
                    print(f"[URL IMPORT] codec={vc} {w}x{h} audio={ac}  needs_normalise={needs_normalise}")
                    log_lines.append(f"Source: codec={vc} {w}x{h} audio={ac}")
            except Exception as pe:
                print(f"[URL IMPORT] probe parse failed: {pe} — normalising to be safe")

            if needs_normalise:
                _st("⏳  Normalising video to 1080×1920 H.264...")
                norm_path = Path(tmpdir) / "normalised_input.mp4"
                norm_cmd = [
                    FFMPEG, "-y", "-threads", "0",
                    "-i", str(src_path),
                    "-vf", (
                        "scale=1080:1920:force_original_aspect_ratio=decrease,"
                        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                        "fps=30"
                    ),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                    "-movflags", "+faststart",
                    str(norm_path)
                ]
                print(f"[URL IMPORT] normalise cmd: {' '.join(norm_cmd[:8])}...")
                norm_result = subprocess.run(
                    norm_cmd, capture_output=True, text=True, timeout=600
                )
                log_lines.append(f"Normalise stdout: {norm_result.stdout[-400:]}")
                log_lines.append(f"Normalise stderr: {norm_result.stderr[-400:]}")
                if norm_result.returncode != 0:
                    print(f"[URL IMPORT] normalise failed rc={norm_result.returncode}")
                    print(f"[URL IMPORT] normalise stderr: {norm_result.stderr[-300:]}")
                    raise RuntimeError(
                        "Video processing failed. The downloaded video format may not be "
                        "compatible. Try a different video."
                    )
                src_path = norm_path
                print(f"[URL IMPORT] Normalised → {src_path.name}")

            # ── Step 6b: CTA concat (direct ffmpeg — bypasses run_export_pipeline) ─
            # We drive each ffmpeg step ourselves so the normalised path goes in
            # without being re-probed or re-encoded by the shared pipeline.
            print("[URL IMPORT] Step 6b: direct CTA concat")
            if not title:
                title = vid_title or "untitled"
            clean_title = name_to_filename(title)
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_path = OUTPUT_DIR / f"{clean_title}.mp4"
            scaled_cta_url  = Path(__file__).parent / "_url_scaled_cta.mp4"

            def _ff(label, cmd, timeout=120):
                print(f"[URL IMPORT] ffmpeg {label}: {' '.join(str(c) for c in cmd[:6])}...")
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                log_lines.append(
                    f"=== ffmpeg {label} ===\n"
                    f"CMD: {' '.join(str(c) for c in cmd)}\n"
                    f"STDERR: {r.stderr[-600:]}\nEXIT: {r.returncode}\n"
                )
                if r.returncode != 0:
                    print(f"[URL IMPORT] ffmpeg {label} failed rc={r.returncode}")
                    print(f"[URL IMPORT] stderr: {r.stderr[-400:]}")
                    raise RuntimeError(
                        f"Video processing failed at {label} (code {r.returncode}). "
                        "Try a different video."
                    )
                print(f"[URL IMPORT] ffmpeg {label} OK")

            try:
                _st("⏳  Mixing voiceover into end card...")
                # Step A: add voiceover to CTA end card
                ra = subprocess.run(
                    [FFPROBE, "-v", "error", "-select_streams", "a:0",
                     "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                     str(CTA_PATH)],
                    capture_output=True, text=True
                )
                cta_has_audio = bool(ra.stdout.strip())
                if cta_has_audio:
                    mix_cmd = [
                        FFMPEG, "-y", "-i", str(CTA_PATH), "-i", str(VOICEOVER_PATH),
                        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest",
                        "-c:v", "copy", str(TEMP_CTA)
                    ]
                else:
                    mix_cmd = [
                        FFMPEG, "-y", "-i", str(CTA_PATH), "-i", str(VOICEOVER_PATH),
                        "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(TEMP_CTA)
                    ]
                _ff("mix-voice", mix_cmd, timeout=60)

                _st("⏳  Scaling end card...")
                # Step B: scale CTA to exact 1080×1920 30fps H.264
                _ff("scale-cta", [
                    FFMPEG, "-y", "-threads", "0", "-i", str(TEMP_CTA),
                    "-vf", (
                        "scale=1080:1920:force_original_aspect_ratio=decrease,"
                        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                        "fps=30"
                    ),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                    str(scaled_cta_url)
                ], timeout=120)

                _st("⏳  Appending end card to video...")
                # Step C: concat normalised main video + scaled CTA
                print(f"[URL IMPORT] concat input 1: {src_path} "
                      f"exists={src_path.exists()} "
                      f"size={src_path.stat().st_size if src_path.exists() else 'MISSING'}")
                print(f"[URL IMPORT] concat input 2: {scaled_cta_url} "
                      f"exists={scaled_cta_url.exists()} "
                      f"size={scaled_cta_url.stat().st_size if scaled_cta_url.exists() else 'MISSING'}")
                print(f"[URL IMPORT] concat output: {output_path}")
                # Use concat demuxer (text file listing inputs) instead of
                # filter_complex concat — far more robust when input files have
                # different colour spaces, pixel formats, or internal parameters.
                concat_list_path = Path(tmpdir) / "concat_list.txt"
                concat_list_path.write_text(
                    f"file '{str(src_path)}'\nfile '{str(scaled_cta_url)}'\n"
                )
                print(f"[URL IMPORT] concat list:\n{concat_list_path.read_text()}")
                _ff("concat", [
                    FFMPEG, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_path),
                    "-vf", "format=yuv420p",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                    str(output_path)
                ], timeout=600)

            finally:
                for _tmp in [TEMP_CTA, scaled_cta_url]:
                    try:
                        if _tmp.exists():
                            _tmp.unlink()
                    except Exception:
                        pass

            print(f"[URL IMPORT] CTA concat done → {output_path}")

            # ── Step 7: upload + schedule ─────────────────────────────────────
            if not has_buffer:
                self._library_save_case(clean_title, output_path, status="Ready",
                                        caption=raw_caption, source_url=url)
                _re_enable()
                _st(f"✓  Done! Saved as {output_path.name}")
                t_total_s = int(time.time() - t_step_start)
                print(f"[{_ts()} URL_IMPORT] Total processing time: {t_total_s}s")
                return

            # Use the approved caption (already edited by user in review dialog)
            caption = raw_caption.strip() if raw_caption else ""
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            _st(f"⏳  Uploading to Archive.org ({file_size_mb:.0f} MB)...")
            t_upload_start = time.time()
            try:
                video_url = upload_video(output_path)
                t_upload_s = int(time.time() - t_upload_start)
                log_lines.append(f"[{_ts()}] Upload OK ({t_upload_s}s): {video_url}")
            except Exception as e:
                log_lines.append(f"[{_ts()}] Upload FAILED: {e}")
                _re_enable()
                _st("Upload failed — check your Internet Archive keys in Settings.", err=True)
                return

            _st("⏳  Scheduling to Buffer...")
            _buffer_scheduled = False
            for _buf_attempt in range(1, 6):
                try:
                    raw_text, result_b = schedule_to_buffer(
                        caption, video_url, bcid, bkey, post_time, due_at_dt=due_dt
                    )
                    log_lines.append(f"[{_ts()}] Buffer attempt {_buf_attempt} raw: {raw_text[:500]}")
                    data = result_b.get("data", {}).get("createPost", {})
                    if "post" in data:
                        due = data["post"].get("dueAt", "")
                        try:
                            dt = datetime.datetime.fromisoformat(due.replace("Z", "+00:00"))
                            local_dt = dt.astimezone()
                            due_fmt = local_dt.strftime("%b %-d at %-I:%M %p")
                        except Exception:
                            due_fmt = due
                        _sv = load_settings(); _sv["last_scheduled_date"] = due; save_settings(_sv)
                        t_total_s = int(time.time() - t_step_start)
                        log_lines.append(f"[{_ts()}] Total time: {t_total_s}s")
                        print(f"[{_ts()} URL_IMPORT] Total processing time: {t_total_s}s")
                        self._library_save_case(
                            clean_title, output_path, status="Scheduled",
                            archive_url=video_url, caption=caption,
                            scheduled_date=due,
                            buffer_post_id=data["post"].get("id", ""),
                            source_url=url,
                        )
                        _buffer_scheduled = True
                        _re_enable()
                        _st(f"✅  Scheduled for {due_fmt}. Archive.org may continue processing in the background.")
                        self.after(0, self._url_prepare_next_import)
                        break
                    else:
                        msg = data.get("message", "unexpected response")
                        log_lines.append(f"[{_ts()}] Buffer attempt {_buf_attempt} error: {msg}")
                        print(f"[{_ts()} URL_IMPORT] Buffer attempt {_buf_attempt}: {msg}")
                        # 404 = Archive.org not ready yet; retry with backoff
                        if buffer_video_not_ready(msg):
                            if _buf_attempt < 5:
                                wait_s = 30 * _buf_attempt
                                _st(f"⏳  Archive.org still processing — retrying in {wait_s}s (attempt {_buf_attempt}/5)...")
                                time.sleep(wait_s)
                                continue
                            else:
                                _re_enable()
                                _st("Archive.org is still processing the video. Try scheduling again in a few minutes.", err=True)
                                break
                        else:
                            _re_enable()
                            _st(f"Buffer error: {msg} — check your Buffer API key in Settings.", err=True)
                            break
                except Exception as e:
                    tb = traceback.format_exc()
                    log_lines.append(f"[{_ts()}] Buffer attempt {_buf_attempt} FAILED: {e}\n{tb}")
                    _re_enable()
                    _st("Failed to schedule to Buffer — check your API key in Settings.", err=True)
                    break

        except RuntimeError as e:
            msg = str(e)
            print(f"[{_ts()} URL_IMPORT] RuntimeError: {msg}")
            log_lines.append(f"[{_ts()}] URL IMPORT RuntimeError: {msg}")
            # Surface a clean message for known failure modes
            if "instagram" in msg.lower() or "login" in msg.lower() or "cookie" in msg.lower():
                _st("Instagram download failed — log in to Instagram in Chrome and retry.", err=True)
            elif "yt-dlp" in msg.lower():
                _st("Download failed — the video may be private or unavailable.", err=True)
            elif "Video processing" in msg or "ffmpeg" in msg.lower():
                _st("Video processing failed — the downloaded format may be incompatible.", err=True)
            else:
                _st(recovery_plain_message(msg), err=True)
            log_recovery_event(
                "URL Import failed",
                "Automatic error translation",
                False,
                "No repair was applied automatically.",
                recovery_plain_message(msg),
            )
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[{_ts()} URL_IMPORT] EXCEPTION: {e}\n{tb}")
            log_lines.append(f"[{_ts()}] URL IMPORT ERROR: {e}\n{tb}")
            clean_msg = recovery_plain_message(str(e))
            _st(clean_msg, err=True)
            log_recovery_event(
                "Unexpected URL Import error",
                "Automatic error translation",
                False,
                "No repair was applied automatically.",
                clean_msg,
            )
        finally:
            print(f"[{_ts()} URL_IMPORT] Thread finally block — re-enabling button")
            _re_enable()
            self._write_log(log_lines)
            if tmpdir:
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass

    # ── Library tab ───────────────────────────────────────────────────────────

    def _build_library_tab(self, parent):
        self._lib_tab = case_library.LibraryTab(parent, self._library)

    def _library_save_case(self, case_name: str, output_path,
                           status: str = "Ready", archive_url: str = "",
                           caption: str = "", scheduled_date: str = "",
                           buffer_post_id: str = "", source_url: str = ""):
        """Save/update a case in the library after a successful export."""
        try:
            self._library.save_case(
                case_name=case_name,
                filename=Path(output_path).name if output_path else "",
                status=status,
                archive_url=archive_url,
                caption=caption,
                scheduled_date=scheduled_date,
                buffer_post_id=buffer_post_id,
                source_url=source_url,
                output_path=output_path,
            )
        except Exception as e:
            print(f"[LIBRARY] save_case failed: {e}")

    # ── Shared footer ─────────────────────────────────────────────────────────

    def _build_footer(self, outer):
        tk.Frame(outer, bg="#1a1a1a", height=1).pack(fill="x", padx=36, pady=(14, 0))

        footer_bar = tk.Frame(outer, bg=BG)
        footer_bar.pack(fill="x", padx=36, pady=(8, 0))

        self._lbl_buffer_status = tk.Label(
            footer_bar, text="", font=("Helvetica", 8), fg=MUTED, bg=BG, anchor="w"
        )
        self._lbl_buffer_status.pack(side="left", fill="x", expand=True)

        settings_border = tk.Frame(footer_bar, bg=CRIMSON, padx=1, pady=1)
        settings_border.pack(side="right")
        btn_settings = _make_lbtn(
            settings_border, "⚙  SETTINGS", self._open_settings,
            bg="#1a1a1a", fg=WHITE, hover_bg="#2a2a2a",
            font=("Helvetica", 9, "bold"), pady=7, padx=16
        )
        btn_settings.pack()
        self._refresh_buffer_status()

        tk.Frame(outer, bg=CRIMSON, height=2).pack(fill="x", pady=(12, 0))
        tk.Label(outer, text="VERDICTIN60  —  NEW CASE. EVERY DAY.",
                 font=("Helvetica", 8, "bold"), fg=CRIMSON, bg=BG).pack(pady=(6, 16))

    def _refresh_buffer_status(self):
        s = load_settings()
        has_buffer = bool(s.get("buffer_key") and s.get("buffer_channel_id"))
        post_time  = s.get("post_time", "18:00")
        if has_buffer:
            self._lbl_buffer_status.config(
                text=f"● Buffer ready  ·  posts at {post_time}", fg="#2d8a4e"
            )
        else:
            self._lbl_buffer_status.config(text="○ Buffer not configured", fg=MUTED)

    def _open_settings(self):
        SettingsDialog(self)
        self._refresh_buffer_status()

    # ── Resize ────────────────────────────────────────────────────────────────

    def _on_resize(self, event):
        if event.widget is not self:
            return
        w, h = event.width, event.height
        if (w, h) == self._last_bg_size:
            return
        self._last_bg_size = (w, h)
        self._bg.delete("all")
        _draw_grain(self._bg, w, h)
        _draw_watermarks(self._bg, w, h)

    # ── Single tab logic ──────────────────────────────────────────────────────

    def _check_ffmpeg(self):
        if not Path(FFMPEG).exists() and shutil.which("ffmpeg") is None:
            self._set_status("ffmpeg not installed — run: brew install ffmpeg", error=True)
            self._btn_select.config(state="disabled")

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Select your case video",
            filetypes=[("Video files", "*.mp4 *.mov"), ("All files", "*.*")]
        )
        if path:
            self.selected_file = Path(path)
            self._lbl_filename.config(text=self.selected_file.name)
            self._card_frame.pack(fill="x", after=self._select_wrap)
            _lbtn_enable(self._btn_export, CRIMSON, WHITE, CRIMSON_HOT)
            self._btn_open.pack_forget()
            self._anim_enter("idle")
            self._anim_status = ""
            self._anim_render()
            self._set_status("")

    def _start_export(self):
        if not self.selected_file:
            return
        title = self._title_var.get().strip()
        if not title:
            self._set_status("Enter a case title before exporting.", error=True)
            return
        raw_caption = self._caption_text.get("1.0", "end").strip()
        if not raw_caption:
            self._set_status("Paste a raw caption before exporting.", error=True)
            return
        _lbtn_disable(self._btn_export, MUTED, "#888888")
        _lbtn_disable(self._btn_select, "#1a1a1a", "#555555")
        self._btn_open.pack_forget()
        self._processing = True
        self._progress.start(10)
        self._set_status("🔴  PROCESSING...")
        self._pulse_dot()
        threading.Thread(
            target=self._run_export,
            args=(name_to_filename(title), raw_caption),
            daemon=True
        ).start()

    def _pulse_dot(self):
        if not self._processing:
            self._dot.config(fg=BG)
            return
        self._dot.config(fg=CRIMSON if self._dot.cget("fg") == BG else BG)
        self.after(600, self._pulse_dot)

    def _run_export(self, title: str, raw_caption: str):
        import traceback
        print(f"[THREAD] Export thread started, thread id: {threading.current_thread().ident}")
        log_lines = []
        output_path = None

        # Read Buffer config up front so we can compute the slot before the
        # heavy ffmpeg step. All of this runs on the background thread.
        s = load_settings()
        bkey = s.get("buffer_key", "")
        bcid = s.get("buffer_channel_id", "")
        post_time = s.get("post_time", "18:00")
        has_buffer = bool(bkey and bcid)
        masked_key = (bkey[:4] + "****") if len(bkey) >= 4 else ("(empty)" if not bkey else bkey)
        log_lines.append("=== SCHEDULING SETUP ===")
        log_lines.append(
            f"Settings: buffer_key={masked_key}  channel_id={'(empty)' if not bcid else bcid}  "
            f"post_time={post_time}  has_buffer={has_buffer}"
        )

        # Step 0: figure out the slot from the Buffer queue (hard 10s cap).
        due_dt = None
        if has_buffer:
            print("[THREAD] Checking Buffer queue...")
            self.after(0, lambda: self._set_status("⏳  Checking Buffer queue..."))
            due_dt = next_available_date_safe(bkey, bcid, post_time, limit_s=10.0)
            print(f"[THREAD] Buffer queue done, slot: {due_dt}")
            local_due = due_dt.astimezone()
            date_str = local_due.strftime("%b %-d, %Y")
            time_str = local_due.strftime("%-I:%M %p")
            log_lines.append(f"Next available slot: {due_dt.isoformat()}")
            self.after(0, lambda: self._set_status(f"📅  Scheduling for {date_str} at {time_str}"))

        # Step 1: ffmpeg pipeline (the heavy step).
        print("[THREAD] Starting pipeline")
        self.after(0, lambda: self._set_status("⏳  Processing video..."))
        try:
            output_path = run_export_pipeline(
                self.selected_file, title, log_lines,
                status_cb=lambda msg: self.after(0, lambda m=msg: self._set_status(m))
            )
        except ExportError as e:
            log_lines.append(f"=== EXPORT ERROR ===\n{e}")
            self._write_log(log_lines)
            self._finish(str(e), success=False)
            return
        except Exception as e:
            log_lines.append(f"=== UNEXPECTED EXCEPTION ===\n{traceback.format_exc()}")
            self._write_log(log_lines)
            self._finish(f"Unexpected error: {e}", success=False)
            return

        print("[THREAD] Pipeline complete")
        self._write_log(log_lines)

        if not has_buffer:
            log_lines.append("Buffer not configured — skipping.")
            self._write_log(log_lines)
            self._library_save_case(title, output_path, status="Ready",
                                    caption=reformat_caption(title, raw_caption))
            self._finish(f"✓  Done! Saved as {output_path.name}", success=True)
            return

        log_lines.append("Step 2: generating caption locally")
        caption = reformat_caption(title, raw_caption)
        log_lines.append(f"Caption generated ({len(caption)} chars)")

        print("[THREAD] Starting upload")
        log_lines.append("Step 3: uploading to Archive.org")
        self.after(0, lambda: self._set_status("⏳  Uploading to Archive.org... (this may take a minute)"))
        try:
            video_url = upload_video(output_path)
            log_lines.append(f"Upload OK: {video_url}")
        except Exception as e:
            log_lines.append(f"Upload FAILED: {e}")
            self._write_log(log_lines)
            self._library_save_case(title, output_path, status="Ready", caption=caption)
            self._finish(
                f"✓  Saved as {output_path.name}  ·  Upload failed — upload manually to Buffer",
                success=True
            )
            return

        print("[THREAD] Upload complete")
        log_lines.append("Step 4: calling Buffer GraphQL API")
        print("[THREAD] Starting Buffer schedule")
        self.after(0, lambda: self._set_status("⏳  Scheduling to Buffer..."))
        try:
            print(f"[BUFFER] Calling schedule_to_buffer with url={video_url[:80]}...")
            raw_text, result = schedule_to_buffer(
                caption, video_url, bcid, bkey, post_time, due_at_dt=due_dt
            )
            print(f"[BUFFER] Raw response: {raw_text[:300]}")
            log_lines.append(f"Buffer raw response: {raw_text[:1000]}")
            log_lines.append(f"Buffer parsed: {result}")
            data = result.get("data", {}).get("createPost", {})
            if "post" in data:
                due = data["post"].get("dueAt", "")
                post_id = data["post"].get("id", "")
                try:
                    dt = datetime.datetime.fromisoformat(due.replace("Z", "+00:00"))
                    local_dt = dt.astimezone()
                    due_fmt  = local_dt.strftime("%b %-d at %-I:%M %p")
                    sched_date = local_dt.strftime("%Y-%m-%d")
                    sched_time = local_dt.strftime("%H:%M")
                except Exception:
                    due_fmt = due; sched_date = due[:10]; sched_time = ""
                print(f"[BUFFER] Success — scheduled for {due_fmt}, post_id={post_id}")
                _s = load_settings(); _s["last_scheduled_date"] = due; save_settings(_s)
                self._library_save_case(title, output_path, status="Scheduled",
                                        archive_url=video_url, caption=caption,
                                        scheduled_date=due, buffer_post_id=post_id)
                self._finish(f"✅  Scheduled for {due_fmt}. Archive.org may continue processing in the background.", success=True)
            elif "message" in data:
                print(f"[BUFFER] Buffer returned error message: {data['message']}")
                self._finish(
                    f"✓  Saved as {output_path.name}  ·  Buffer error: {data['message']}",
                    success=True
                )
            else:
                print(f"[BUFFER] Unexpected response structure: {result}")
                self._finish(
                    f"✓  Saved as {output_path.name}  ·  Buffer: unexpected response",
                    success=True
                )
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            print(f"[BUFFER] EXCEPTION:\n{tb}")
            log_lines.append(f"Buffer FAILED: {e}\n{tb}")
            self._finish(
                f"✓  Saved as {output_path.name}  ·  Buffer failed: {e}",
                success=True
            )
        finally:
            self._write_log(log_lines)

    def _write_log(self, log_lines):
        try:
            LOG_PATH.write_text("\n".join(log_lines))
        except Exception:
            pass

    def _finish(self, message, success):
        self._processing = False
        self._progress.stop()
        self.after(0, lambda: self._set_status(message, error=not success))
        def _re_enable_export():
            if self.selected_file:
                _lbtn_enable(self._btn_export, CRIMSON, WHITE, CRIMSON_HOT)
            else:
                _lbtn_disable(self._btn_export, MUTED, "#888888")
            _lbtn_enable(self._btn_select, "#1a1a1a", WHITE, "#2a2a2a")
        self.after(0, _re_enable_export)
        if success:
            self.after(0, self._show_open_btn)

    def _show_open_btn(self):
        self._btn_open.pack(pady=(16, 0))

    # ── Canvas animation ──────────────────────────────────────────────────────

    def _anim_enter(self, state):
        if state == self._anim_state and state not in ("success",):
            return
        if self._anim_tick_id:
            self.after_cancel(self._anim_tick_id)
            self._anim_tick_id = None
        self._anim_state = state
        self._anim_phase = 0.0
        if state in ("processing", "scheduling"):
            self._anim_tick()
        elif state == "success":
            self._anim_success_tick()

    def _anim_tick(self):
        if self._anim_state not in ("processing", "scheduling"):
            return
        self._anim_phase = (self._anim_phase + 0.018) % 1.0
        self._anim_render()
        self._anim_tick_id = self.after(40, self._anim_tick)

    def _anim_success_tick(self):
        self._anim_phase += 0.04
        self._anim_render()
        if self._anim_phase < 1.0:
            self._anim_tick_id = self.after(16, self._anim_success_tick)

    def _anim_render(self):
        _draw_anim(self._anim_canvas, self._anim_state, self._anim_phase,
                   self._anim_status, idle_hint="Select a case file to begin")

    def _url_anim_render(self):
        _draw_anim(self._url_anim_canvas, self._url_anim_state, self._url_anim_phase,
                   self._url_anim_status, idle_hint="Paste a URL and hit Import")

    def _set_status(self, text, error=False):
        self._lbl_status.config(text=text, fg=ERROR_RED if error else LIGHT_GRAY)
        self._anim_status = text
        if error:
            self._anim_enter("error")
        elif not text:
            self._anim_enter("idle")
        elif "✅" in text or "Scheduled for" in text:
            self._anim_enter("success")
        elif "Buffer" in text or "Scheduling" in text:
            self._anim_enter("scheduling")
        elif text:
            if self._anim_state not in ("processing", "scheduling", "success"):
                self._anim_enter("processing")
        self._anim_render()

    def _open_output_folder(self):
        subprocess.Popen(["open", str(OUTPUT_DIR)])


if __name__ == "__main__":
    app = App()
    app.mainloop()
