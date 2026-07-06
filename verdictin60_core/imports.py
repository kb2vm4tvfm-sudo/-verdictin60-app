"""URL/DOCX import helpers, moved from app.py (Phase 2 refactor, no behavior change).

- ytdlp_cmd: build a yt-dlp command that works when launched from Dock or Terminal.
- parse_docx_queue: read a DOCX table with columns URL / Case Title / Caption.
- download_video_url: download a URL with yt-dlp using browser-cookie fallbacks.

Batch URL ingestion helpers (issue #72), used when the user pastes/imports a
plain list of URLs into Batch instead of preparing a DOCX queue:

- parse_url_list: extract a deduped list of URLs from pasted text or an
  imported .txt/.csv file's contents.
- probe_url_metadata: best-effort yt-dlp metadata probe (no download) for a
  title/description.
- fetch_page_title: best-effort HTML <title> fetch for non-video URLs that
  yt-dlp can't handle (e.g. news articles).
- title_from_url: last-resort title guess derived only from the URL path.
"""
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse


def ytdlp_cmd(extra_args: list[str]) -> list[str]:
    """Return a yt-dlp command that works when launched from Dock or Terminal."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0:
            return [sys.executable, "-m", "yt_dlp"] + extra_args
    except Exception:
        pass

    ytdlp_bin = shutil.which("yt-dlp")
    if not ytdlp_bin:
        for candidate in [
            "/Library/Frameworks/Python.framework/Versions/3.14/bin/yt-dlp",
            "/usr/local/bin/yt-dlp",
            "/opt/homebrew/bin/yt-dlp",
        ]:
            if Path(candidate).exists():
                ytdlp_bin = candidate
                break
    ytdlp_bin = ytdlp_bin or "yt-dlp"
    return [ytdlp_bin] + extra_args


def parse_docx_queue(docx_path: Path) -> list[dict]:
    """Read a DOCX table with columns: URL / Case Title / Caption."""
    import zipfile
    import xml.etree.ElementTree as ET

    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }

    def _rels(zf) -> dict:
        try:
            root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        except Exception:
            return {}
        rels = {}
        for rel in root.findall("rel:Relationship", ns):
            rid = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if rid and target:
                rels[rid] = target
        return rels

    def _cell_text(cell, rels: dict) -> str:
        parts = []
        for p in cell.findall(".//w:p", ns):
            p_bits = []
            for node in p.iter():
                if node.tag == f"{{{ns['w']}}}t" and node.text:
                    p_bits.append(node.text)
                elif node.tag == f"{{{ns['w']}}}tab":
                    p_bits.append(" ")
                elif node.tag == f"{{{ns['w']}}}br":
                    p_bits.append("\n")
            paragraph = "".join(p_bits).strip()
            if paragraph:
                parts.append(paragraph)

        text = "\n".join(parts).strip()
        for link in cell.findall(".//w:hyperlink", ns):
            rid = link.attrib.get(f"{{{ns['r']}}}id")
            target = rels.get(rid, "")
            if target.startswith("http") and target not in text:
                text = f"{target}\n{text}".strip()
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    rows = []
    with zipfile.ZipFile(docx_path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        rels = _rels(zf)
        for table in root.findall(".//w:tbl", ns):
            for tr in table.findall("./w:tr", ns):
                cells = tr.findall("./w:tc", ns)
                if len(cells) < 3:
                    continue
                values = [_cell_text(c, rels) for c in cells[:3]]
                url, title, caption = [v.strip() for v in values]
                header = f"{url} {title} {caption}".lower()
                if "url" in header and "case" in header and "caption" in header:
                    continue
                if not url or not title or not caption:
                    continue
                url_match = re.search(r"https?://\S+", url)
                if not url_match:
                    continue
                rows.append({
                    "url": url_match.group(0).rstrip(").,"),
                    "title": title,
                    "caption": caption,
                })
    return rows


def download_video_url(url: str, outdir: Path, settings: dict, log_lines: list,
                       timeout: int = 240) -> Path:
    """Download a URL with yt-dlp using browser-cookie fallbacks."""
    outdir.mkdir(parents=True, exist_ok=True)
    preferred = settings.get("preferred_browser", "chrome")
    fallbacks = [b for b in ("chrome", "safari", "firefox") if b != preferred]
    browser_order = [preferred] + fallbacks + [None]
    last_result = None
    for browser in browser_order:
        cookie_args = ["--cookies-from-browser", browser] if browser else []
        cmd = ytdlp_cmd(cookie_args + [
            "--no-playlist",
            "-f", "bv*+ba/best",
            "--merge-output-format", "mp4",
            "-o", str(outdir / "%(title).80s.%(ext)s"),
            url,
        ])
        log_lines.append(f"yt-dlp download browser={browser}: {' '.join(cmd[:8])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        last_result = result
        log_lines.append(f"yt-dlp rc={result.returncode} browser={browser}")
        if result.returncode == 0:
            files = [
                p for p in outdir.iterdir()
                if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm", ".mkv")
            ]
            if files:
                return max(files, key=lambda p: p.stat().st_mtime)
    stderr = (last_result.stderr if last_result else "")[:400]
    raise RuntimeError(f"Video download failed. {stderr}")


_URL_RE = re.compile(r'https?://[^\s,"\']+')


def parse_url_list(text: str) -> list[str]:
    """Extract a deduped list of URLs from pasted text or an imported
    .txt/.csv file's contents. One URL per line, comma, or plain whitespace
    all work — the match stops at whitespace, commas, or quotes so a
    comma-separated (CSV) line of multiple URLs doesn't get merged into one
    string; trailing punctuation commonly picked up from prose is stripped."""
    seen = set()
    urls = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip('.,;)>]"\'')
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def probe_url_metadata(url: str, settings: dict, timeout: int = 20) -> dict:
    """Best-effort metadata probe for a batch URL import — does NOT download
    media, just asks yt-dlp to report what it knows about the URL. Uses the
    same browser-cookie fallback order as download_video_url so login-gated
    sources still resolve. Returns {"title", "description", "error"}; "error"
    is empty on success. Never raises — callers get a clear reason instead."""
    preferred = settings.get("preferred_browser", "chrome")
    fallbacks = [b for b in ("chrome", "safari", "firefox") if b != preferred]
    browser_order = [preferred] + fallbacks + [None]
    last_err = ""
    for browser in browser_order:
        cookie_args = ["--cookies-from-browser", browser] if browser else []
        cmd = ytdlp_cmd(cookie_args + [
            "--no-playlist", "--skip-download", "--dump-single-json", "--no-warnings", url,
        ])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except Exception as e:
            last_err = str(e)
            continue
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip().splitlines()[-1])
            except Exception as e:
                last_err = f"could not parse yt-dlp output: {e}"
                continue
            return {
                "title": (data.get("title") or "").strip(),
                "description": (data.get("description") or "").strip(),
                "error": "",
            }
        last_err = (result.stderr or "").strip()[:300] or "yt-dlp returned no data"
    return {"title": "", "description": "", "error": last_err}


def fetch_page_title(url: str, timeout: int = 10) -> str:
    """Best-effort HTML <title> fetch for URLs yt-dlp can't handle (e.g. news
    articles rather than video hosts). Reads only the first chunk of the
    response so a large page can't stall batch URL detection. Never raises —
    returns "" on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            chunk = r.read(200_000).decode(charset, errors="ignore")
    except Exception:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", chunk, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200]


def title_from_url(url: str) -> str:
    """Last-resort, purely-local title guess derived from the URL path, used
    when yt-dlp metadata probing and the page <title> both fail."""
    path = urlparse(url).path
    slug = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    slug = unquote(slug).replace("-", " ").replace("_", " ").strip()
    slug = re.sub(r"\s+", " ", slug)
    return slug.title() if slug else ""
