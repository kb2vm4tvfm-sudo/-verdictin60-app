"""URL/DOCX import helpers, moved from app.py (Phase 2 refactor, no behavior change).

- ytdlp_cmd: build a yt-dlp command that works when launched from Dock or Terminal.
- parse_docx_queue: read a DOCX table with columns URL / Case Title / Caption.
- download_video_url: download a URL with yt-dlp using browser-cookie fallbacks.
- parse_ytdlp_metadata: pull title/uploader/description/tags out of a yt-dlp
  ``--dump-json`` metadata dict.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path


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


def parse_ytdlp_metadata(meta: dict) -> tuple[str, str, str, str]:
    """Pull (title, uploader, full_text, tags) out of a yt-dlp --dump-json dict."""
    vid_title = meta.get("title", "") or ""
    uploader = (
        meta.get("uploader")
        or meta.get("uploader_id")
        or meta.get("channel")
        or ""
    )
    full_text = (
        meta.get("description") or
        meta.get("comment") or
        meta.get("title") or
        meta.get("fulltitle") or
        meta.get("webpage_url_basename") or
        ""
    )
    tags = ", ".join(meta.get("tags", []) or [])
    return vid_title, uploader, full_text, tags
