"""Lightweight source metadata extraction for the Batch tab "Add Videos"
workflow (issue #77).

Deliberately minimal: the old Research Hub / research.py verification
pipeline was removed (see app.py's Phase 9 refactor note), so this module
only pulls the cheap, safe signals the caption pipeline needs — yt-dlp
metadata for video URLs, a plain page-title fetch for anything yt-dlp can't
parse, and ffprobe tags for local files. None of this calls a paid provider,
so it isn't subject to the AI cost/quota guard.
"""
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from verdictin60_core.imports import ytdlp_cmd

FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

EMPTY_METADATA = {"title": "", "description": "", "uploader": "", "page_title": ""}

# Instagram serves a generic placeholder page (no real post content) to
# logged-out/blocked requests, but still returns 200 with a bare <title> like
# "Instagram" or a login prompt. Without this check that placeholder gets
# mistaken for real metadata - it becomes the case title AND the caption
# "description", producing a useless caption that just says "Instagram".
_BLOCKED_INSTAGRAM_TITLE_RE = re.compile(
    r"^\s*(instagram(\s*[•\-|]\s*photos and videos)?|log ?in\s*[•\-|]?\s*instagram|instagram\s*[•\-|]?\s*log ?in)\s*$",
    re.IGNORECASE,
)


def _looks_like_blocked_instagram_page(url: str, page_title: str) -> bool:
    return "instagram.com" in url.lower() and bool(_BLOCKED_INSTAGRAM_TITLE_RE.match(page_title))


def fetch_url_metadata(url: str, timeout: int = 25) -> dict:
    """Best-effort metadata for a video URL: yt-dlp first, then a raw page-title
    fetch if yt-dlp can't parse the page (e.g. a news article rather than a video)."""
    meta = dict(EMPTY_METADATA)
    try:
        cmd = ytdlp_cmd(["--skip-download", "--dump-single-json", "--no-playlist", url])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            meta["title"] = (data.get("title") or "").strip()
            meta["description"] = (data.get("description") or "").strip()
            meta["uploader"] = (data.get("uploader") or data.get("channel") or "").strip()
    except Exception:
        pass

    if not meta["title"] and not meta["description"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=min(timeout, 10)) as r:
                html = r.read(200_000).decode("utf-8", errors="ignore")
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if m:
                page_title = re.sub(r"\s+", " ", m.group(1)).strip()
                if not _looks_like_blocked_instagram_page(url, page_title):
                    meta["page_title"] = page_title
        except Exception:
            pass

    return meta


def probe_local_video(path: Path) -> dict:
    """Best-effort metadata for a local video file: ffprobe format tags, else
    just the filename (the caller falls back to that for the case title)."""
    meta = dict(EMPTY_METADATA)
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format_tags=title,description",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            tags = json.loads(result.stdout).get("format", {}).get("tags", {}) or {}
            meta["title"] = (tags.get("title") or "").strip()
            meta["description"] = (tags.get("description") or "").strip()
    except Exception:
        pass
    return meta
