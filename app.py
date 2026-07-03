"""VerdictIn60 desktop app entry point — orchestrates the Tk UI tabs and wires them to verdictin60_core/verdictin60_ui."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms-playwright")
)

import tkinter as tk
from tkinter import filedialog
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
from verdictin60_core.scheduling import batch_post_datetime, _date_at_post_time
from verdictin60_core.captions import caption_needs_fallback
from verdictin60_core.imports import (
    ytdlp_cmd, parse_docx_queue, download_video_url, parse_ytdlp_metadata,
)
from verdictin60_core.export import ExportError, run_export_pipeline
from verdictin60_core.ai import (
    get_ai_speed_mode, get_ai_model,
    is_timeout_error, check_ollama, check_ollama_model_installed,
    ollama_generate, ollama_identify,
)
from verdictin60_core.research import (
    fetch_wikipedia_summary, gather_verification_sources,
    format_sources_for_prompt, format_blocked_sources_for_prompt,
    verification_confidence, build_verified_fact_sheet,
    source_section_for_caption,
)
from verdictin60_core.publishing import (
    fetch_buffer_scheduled_texts, next_available_date_safe,
    upload_video, schedule_to_buffer, buffer_video_not_ready,
    wait_for_public_video_url,
)
from verdictin60_core.recovery import (
    log_recovery_event, scan_recovery_health, recovery_plain_message,
)
from verdictin60_core.utils import _ts, write_log_lines
from verdictin60_ui.widgets import (
    BG, CRIMSON, CRIMSON_HOT, ERROR_RED, WHITE, OFF_WHITE, MUTED, LIGHT_GRAY,
    _make_lbtn, _lbtn_enable, _lbtn_disable,
)
from verdictin60_ui.settings_tab import SettingsDialog
from verdictin60_ui.single_export_tab import build_single_tab
from verdictin60_ui.batch_tab import build_batch_tab
from verdictin60_ui.url_import_tab import build_url_tab
from verdictin60_ui.library_tab import build_library_tab
from verdictin60_ui.recovery_tab import build_recovery_tab

ASSETS_DIR    = Path(__file__).parent / "assets"
OUTPUT_DIR    = Path(__file__).parent / "finished-reels"
CTA_PATH      = ASSETS_DIR / "cta-endcard.mp4"
VOICEOVER_PATH= ASSETS_DIR / "voiceover.mp3"
LOGO_PATH     = ASSETS_DIR / "logo.png"
TEMP_CTA      = Path(__file__).parent / "cta-with-voice.mp4"
LOG_PATH      = Path(__file__).parent / "export-log.txt"
IMPORT_DOCX_PATH = Path(__file__).parent / "VerdictIn60_Import_With_Captions.docx"

FFMPEG      = shutil.which("ffmpeg")  or "/opt/homebrew/bin/ffmpeg"
FFPROBE     = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
DEFAULT_HASHTAGS = "#truecrime #verdictin60 #truecrimecommunity #coldcase #crimejunkie #justice #realcrimecases #crimeawareness #crimearchive #truecrimestories #crimeanalysis #lawandcrime #casefile #truecrimeobsessed #victimsmatter #crimebreakdown #truecrimefacts #truestoryreels #crimecommunity #crimehistory"

# ── Settings ──────────────────────────────────────────────────────────────────
# load_settings/save_settings moved to verdictin60_core.settings (Phase 1 refactor).
# ytdlp_cmd/parse_docx_queue/download_video_url moved to verdictin60_core.imports
# (Phase 2 refactor).
# AI_SPEED_MODES and the Ollama/AI helpers below moved to verdictin60_core.ai
# (Phase 4 refactor).
# Source research/verification helpers moved to verdictin60_core.research
# (Phase 5 refactor).


# ── Rule-Based Recovery Assistant ─────────────────────────────────────────────
# _recovery_history/log_recovery_event/_recovery_issue/scan_recovery_health/
# recovery_plain_message moved to verdictin60_core.recovery (Phase 7 refactor).


# ── Instagram / Meta API ──────────────────────────────────────────────────────
# instagram_connect/autodetect_instagram_id/fetch_ig_media_metrics moved to
# verdictin60_core.publishing (Phase 6 refactor).


# ── Name cleaning ─────────────────────────────────────────────────────────────

# name_to_filename/filename_to_display moved to verdictin60_core.paths (Phase 1 refactor).


# ── Scheduling helpers ────────────────────────────────────────────────────────
# next_post_datetime/batch_post_datetime/_date_at_post_time moved to
# verdictin60_core.scheduling (Phase 1 refactor).


# _resolve_buffer_org_id/fetch_buffer_scheduled_texts/get_next_available_date/
# next_available_date_safe moved to verdictin60_core.publishing (Phase 6 refactor).


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


def reformat_caption(case_title: str, raw_caption: str) -> str:
    text = raw_caption.strip()
    text = re.sub(r'follow @\S+.*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'#\w+(\s+#\w+)*\s*$', '', text, flags=re.MULTILINE).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
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
    source = re.sub(r'\[?#([A-Za-z0-9_]+)\]?\([^)]+\)', r'#\1', source)
    source = re.sub(r'https?://\S+', '', source)
    source = re.sub(r'#\w+', '', source).strip()
    source = re.sub(r'\s+', ' ', source)

    sentences = [
        s.strip()
        for s in re.split(r'(?<=[.!?])\s+', source)
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
# upload_video/schedule_to_buffer/buffer_video_not_ready/public_url_http_code/
# wait_for_public_video_url/UploadPendingError moved to verdictin60_core.publishing
# (Phase 6 refactor).


# ── Dialogs ───────────────────────────────────────────────────────────────────
# SettingsDialog moved to verdictin60_ui.settings_tab (Phase 8 refactor).


# ── Timestamp helper ──────────────────────────────────────────────────────────
# _ts moved to verdictin60_core.utils (Phase 7 refactor).


# ── Source research and verification helpers ──────────────────────────────────
# fetch_wikipedia_summary, gather_verification_sources, format_sources_for_prompt,
# format_blocked_sources_for_prompt, verification_confidence, build_verified_fact_sheet,
# and source_section_for_caption (plus their low-level fetch/search/classify helpers)
# moved to verdictin60_core.research (Phase 5 refactor).


# ── Shared canvas animation drawing ──────────────────────────────────────────
def _draw_anim(c, state, phase, status_txt, idle_hint=""):
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
        open_amt = max(0.0, math.sin(phase * math.pi * 2)) ** 0.6
    elif state == "scheduling":
        open_amt = 0.75 + 0.05 * math.sin(phase * math.pi * 4)
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
        pulse = (math.sin(phase * math.pi * 6) + 1) / 2
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
    """Root Tk window: builds the tab UI and orchestrates export/import/batch/recovery workflows."""

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

        build_single_tab(self, self._single_frame)
        build_batch_tab(self, self._batch_frame)
        build_url_tab(self, self._url_frame)
        build_library_tab(self, self._library_frame)
        build_recovery_tab(self, self._recovery_frame)

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

    # ── Recovery tab ──────────────────────────────────────────────────────────
    # _build_recovery_tab moved to verdictin60_ui.recovery_tab (Phase 8 refactor).

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

    # ── Batch tab ─────────────────────────────────────────────────────────────
    # _build_batch_tab moved to verdictin60_ui.batch_tab (Phase 8 refactor).

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
    # _build_url_tab moved to verdictin60_ui.url_import_tab (Phase 8 refactor).

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
    # _build_library_tab moved to verdictin60_ui.library_tab (Phase 8 refactor).

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
    # _build_single_tab moved to verdictin60_ui.single_export_tab (Phase 8 refactor).

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
            tb = traceback.format_exc()
            print(f"[BUFFER] EXCEPTION:\n{tb}")
            log_lines.append(f"Buffer FAILED: {e}\n{tb}")
            self._finish(
                f"✓  Saved as {output_path.name}  ·  Buffer failed: {e}",
                success=True
            )
        finally:
            self._write_log(log_lines)

    def _write_log(self, log_lines):
        write_log_lines(LOG_PATH, log_lines)

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
