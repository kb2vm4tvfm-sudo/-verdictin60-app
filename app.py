"""VerdictIn60 desktop app entry point — orchestrates the Tk UI tabs and wires them to verdictin60_core/verdictin60_ui."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms-playwright")
)

import tkinter as tk
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
    ytdlp_cmd, download_video_url,
)
from verdictin60_core.metadata import fetch_url_metadata, probe_local_video
from verdictin60_core.caption_pipeline import generate_case_caption, READY
from verdictin60_core.batch_items import parse_pasted_urls
from verdictin60_core.export import ExportError, run_export_pipeline
from verdictin60_core.publishing import (
    next_available_date_safe,
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
from verdictin60_ui.theme import (
    SIDEBAR_BG, SIDEBAR_WIDTH, BORDER, BORDER_LIGHT, INPUT_BG,
    CARD_ALT, CARD_HOVER, TEXT_SECONDARY, TEXT_DIM, TEXT_MUTED, FONT_FAMILY,
    CARD, SURFACE, SUCCESS, WARNING, WARNING_BG,
)
from verdictin60_ui.components import (
    make_sidebar_button, set_sidebar_active, set_sidebar_inactive, make_badge, make_top_bar,
    stop_loading_state, make_error_banner, make_source_list, make_card, card_body,
    make_confidence_badge, make_toplevel_shell, STATUS_STYLES,
)
from verdictin60_ui.settings_tab import SettingsDialog
from verdictin60_ui.batch_tab import build_batch_tab
from verdictin60_ui.recovery_tab import build_recovery_tab

ASSETS_DIR    = Path(__file__).parent / "assets"
OUTPUT_DIR    = Path(__file__).parent / "finished-reels"
CTA_PATH      = ASSETS_DIR / "cta-endcard.mp4"
VOICEOVER_PATH= ASSETS_DIR / "voiceover.mp3"
LOGO_PATH     = ASSETS_DIR / "logo.png"
TEMP_CTA      = Path(__file__).parent / "cta-with-voice.mp4"
LOG_PATH      = Path(__file__).parent / "export-log.txt"

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
    c = INPUT_BG
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
            shade = CARD if (gx // 18 + gy // 18) % 2 == 0 else SURFACE
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
# The URL Import / Research Hub feature set (and its research.py-backed
# verification pipeline) was removed; only the Batch/Recovery/Settings tabs
# remain (Phase 9 refactor).


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
        self.after(0, self._maximize)

    def _maximize(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

    # ── Root layout ───────────────────────────────────────────────────────────

    NAV_ITEMS = [
        ("batch",    "▤", "BATCH"),
        ("recovery", "⛭", "RECOVERY"),
    ]

    def _build_ui(self):
        self._bg = tk.Canvas(self, bg=BG, highlightthickness=0)
        self._bg.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.bind("<Configure>", self._on_resize)

        shell = tk.Frame(self, bg=BG)
        shell.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # ── Sidebar navigation ───────────────────────────────────────────────
        sidebar = tk.Frame(shell, bg=SIDEBAR_BG, width=SIDEBAR_WIDTH)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(shell, bg=BORDER, width=1).pack(side="left", fill="y")

        logo_area = tk.Frame(sidebar, bg=SIDEBAR_BG)
        logo_area.pack(fill="x", pady=(24, 4))

        logo_loaded = False
        try:
            from PIL import Image, ImageTk
            raw = Image.open(LOGO_PATH)
            raw.thumbnail((150, 70), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(raw)
            tk.Label(logo_area, image=self._logo_img, bg=SIDEBAR_BG).pack()
            logo_loaded = True
        except Exception:
            pass

        if not logo_loaded:
            tk.Label(logo_area, text="VERDICTIN60",
                     font=("Helvetica", 18, "bold"), fg=WHITE, bg=SIDEBAR_BG).pack()

        tk.Label(sidebar, text="N E W  C A S E .  E V E R Y  D A Y .",
                 font=("Helvetica", 7, "bold"), fg=CRIMSON, bg=SIDEBAR_BG).pack(pady=(2, 16))

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 12))

        nav_frame = tk.Frame(sidebar, bg=SIDEBAR_BG)
        nav_frame.pack(fill="x")

        self._nav_rows = {}
        for key, icon, label in self.NAV_ITEMS:
            row = make_sidebar_button(nav_frame, icon, label, lambda k=key: self._switch_tab(k))
            row.pack(fill="x")
            self._nav_rows[key] = row

        tk.Frame(sidebar, bg=SIDEBAR_BG).pack(fill="both", expand=True)  # spacer pushes settings down

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 4))
        settings_row = make_sidebar_button(sidebar, "⚙", "SETTINGS", self._open_settings)
        settings_row.pack(fill="x", pady=(0, 16))

        # ── Content column ───────────────────────────────────────────────────
        self._outer = outer = tk.Frame(shell, bg=BG)
        outer.pack(side="left", fill="both", expand=True)

        top_bar, self._top_bar_title = make_top_bar(outer)
        top_bar.pack(fill="x")
        tk.Frame(outer, bg=BORDER, height=1).pack(fill="x")

        # ── Tab content frames ────────────────────────────────────────────────
        self._batch_frame    = tk.Frame(outer, bg=BG)
        self._recovery_frame = tk.Frame(outer, bg=BG)
        self._batch_frame.pack(fill="both", expand=True)
        # recovery frame hidden initially

        build_batch_tab(self, self._batch_frame)
        build_recovery_tab(self, self._recovery_frame)

        # ── Shared footer ─────────────────────────────────────────────────────
        self._build_footer(outer)

        self._switch_tab("batch")

    _NAV_TITLES = {
        "batch":    "BATCH",
        "recovery": "RECOVERY",
    }

    def _switch_tab(self, tab: str):
        for f in (self._batch_frame, self._recovery_frame):
            f.pack_forget()
        for key, row in self._nav_rows.items():
            set_sidebar_active(row) if key == tab else set_sidebar_inactive(row)
        self._top_bar_title.config(text=self._NAV_TITLES.get(tab, ""))
        if tab == "batch":
            self._batch_frame.pack(fill="both", expand=True)
        elif tab == "recovery":
            self._recovery_frame.pack(fill="both", expand=True)

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
            fg=ERROR_RED if attention else SUCCESS
        )
        for issue in issues:
            self._recovery_add_row(issue)

    def _recovery_add_row(self, issue: dict):
        severity = issue.get("severity", "ok")
        accent = SUCCESS if severity == "ok" else CRIMSON
        row = tk.Frame(
            self._recovery_results, bg=CARD_ALT,
            highlightthickness=1, highlightbackground=BORDER
        )
        row.pack(fill="x", pady=(0, 8))

        left = tk.Frame(row, bg=CARD_ALT)
        left.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        header_row = tk.Frame(left, bg=CARD_ALT)
        header_row.pack(anchor="w", fill="x")
        tk.Label(header_row, text=f"{issue['area']}  ·  {issue['status']}",
                 bg=CARD_ALT, fg=accent,
                 font=("Helvetica", 10, "bold")).pack(side="left")
        make_badge(
            header_row, "OK" if severity == "ok" else severity.upper(),
            status="success" if severity == "ok" else ("warning" if severity == "warning" else "error"),
        ).pack(side="left", padx=(8, 0))
        tk.Label(left, text=issue["problem"],
                 bg=CARD_ALT, fg=WHITE,
                 font=("Helvetica", 10), wraplength=470,
                 justify="left").pack(anchor="w", pady=(3, 0))
        tk.Label(left, text=issue["why"],
                 bg=CARD_ALT, fg=LIGHT_GRAY,
                 font=("Helvetica", 9), wraplength=470,
                 justify="left").pack(anchor="w", pady=(3, 0))

        if issue.get("action"):
            _make_lbtn(
                row, "REPAIR", lambda i=issue: self._recovery_confirm_repair(i),
                bg=INPUT_BG, fg=WHITE, hover_bg=BORDER,
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
            result_lbl.config(text=f"{result}\n{verification}", fg=SUCCESS)
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
            bg=BORDER, fg=WHITE, hover_bg=BORDER_LIGHT,
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

    def _batch_add_items(self, urls: list, paths: list):
        """The Add Videos workflow's single entry point: one batch item per
        URL/local file, each researched and captioned independently in the
        background so one failure doesn't hold up (or stop) the others."""
        new_rows = []
        for p in paths:
            self._batch_add_row(path=Path(p))
            new_rows.append(self._batch_rows[-1])
        for u in urls:
            self._batch_add_row(url=u)
            new_rows.append(self._batch_rows[-1])
        self._refresh_batch_ui()
        for row in new_rows:
            threading.Thread(target=self._process_batch_new_item, args=(row,), daemon=True).start()

    def _set_row_status(self, row: dict, msg: str, color=LIGHT_GRAY):
        self.after(0, lambda: row["status_lbl"].config(text=msg, fg=color))

    # proc_status (the gating state _start_batch checks) -> (badge text, STATUS_STYLES key)
    _BADGE_DISPLAY = {
        "queued":       ("QUEUED", "neutral"),
        "working":      ("WORKING", "info"),
        "ready":        ("READY", "success"),
        "needs_review": ("NEEDS REVIEW", "warning"),
        "error":        ("ERROR", "error"),
    }

    def _set_row_badge(self, row: dict, proc_status: str):
        row["proc_status"] = proc_status
        text, style = self._BADGE_DISPLAY.get(proc_status, self._BADGE_DISPLAY["queued"])
        fg, bg = STATUS_STYLES.get(style, STATUS_STYLES["neutral"])
        self.after(0, lambda: row["badge_lbl"].config(text=f" {text} ", fg=fg, bg=bg))
        self.after(0, lambda: self._update_row_review_widgets(row))

    def _update_row_review_widgets(self, row: dict):
        """Reflect proc_status/review_reason on the row's Review button and
        reason line — a Needs Review row shows why, and offers a Review
        button to open/edit/approve it (issue #79)."""
        if row["proc_status"] == "needs_review":
            reason = row.get("review_reason") or "manual verification recommended"
            row["reason_lbl"].config(text=f"⚠  Needs review — {reason}")
            row["review_btn"].config(text=" REVIEW ▸ ")
        else:
            row["reason_lbl"].config(text="")
            row["review_btn"].config(text=" EDIT ")

    def _process_batch_new_item(self, row: dict):
        """Research + generate a VerdictIn60-style caption for one newly-added
        batch row. Runs off the UI thread; any failure here is caught and
        surfaced on the row itself rather than raised, so it can't take down
        the rest of the batch."""
        path = row.get("path")
        url = row.get("url", "")
        log_lines = []
        try:
            self._set_row_status(row, "🔎  Researching…")
            self._set_row_badge(row, "working")
            try:
                metadata = probe_local_video(path) if path else fetch_url_metadata(url)
            except Exception as e:
                metadata = {}
                log_lines.append(f"Metadata fetch failed: {e}")

            title = row["case_var"].get().strip()
            if not title:
                detected = metadata.get("title") or metadata.get("page_title")
                detected = detected or (path.stem if path else url)
                title = filename_to_display(name_to_filename(detected))
                self.after(0, lambda t=title: row["case_var"].set(t))

            self._set_row_status(row, "✍️  Writing caption…")
            caption, status, review_reason = generate_case_caption(title, metadata, url, log_lines)

            def _apply(c=caption):
                row["caption_text"].delete("1.0", "end")
                row["caption_text"].insert("1.0", c)
            self.after(0, _apply)

            if status == READY:
                row["review_reason"] = ""
                self._set_row_status(row, "✓  Caption ready", SUCCESS)
                self._set_row_badge(row, "ready")
            else:
                row["review_reason"] = review_reason
                self._set_row_status(
                    row, f"⚠  Needs review — {review_reason}. Click Review to fix.", WARNING
                )
                self._set_row_badge(row, "needs_review")
        except Exception as e:
            self._set_row_status(row, f"✗  Failed: {e}", ERROR_RED)
            self._set_row_badge(row, "error")

    def _batch_add_row(self, path: Path = None, url: str = "",
                       case_title: str = "", caption: str = "",
                       final_caption: bool = True):
        idx = len(self._batch_rows)
        bg = CARD_ALT if idx % 2 == 0 else CARD_HOVER

        frame = make_card(self._batch_list_frame, padx=10, pady=8, bg=bg, border=BORDER)
        frame.pack(fill="x", padx=8, pady=4)
        inner = card_body(frame)

        # Source label (truncated)
        source_name = path.stem if path else re.sub(r"^https?://", "", url)
        fname = source_name[:22] + "…" if len(source_name) > 22 else source_name
        tk.Label(inner, text=fname, font=(FONT_FAMILY, 8), fg=TEXT_SECONDARY,
                 bg=bg, width=20, anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 8))

        # Case title entry
        initial_title = case_title or (filename_to_display(name_to_filename(path.stem)) if path else "")
        case_var = tk.StringVar(value=initial_title)
        title_entry = tk.Entry(inner, textvariable=case_var,
                               font=(FONT_FAMILY, 9), fg=WHITE, bg=INPUT_BG,
                               insertbackground=WHITE, relief="flat",
                               highlightthickness=1, highlightbackground=BORDER,
                               highlightcolor=CRIMSON)
        title_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        # Status badge (verification/caption readiness — set by _set_row_badge)
        fg, badge_bg = STATUS_STYLES["neutral"]
        badge_lbl = tk.Label(inner, text=" QUEUED ", font=(FONT_FAMILY, 7, "bold"),
                             fg=fg, bg=badge_bg, anchor="center")
        badge_lbl.grid(row=0, column=2, padx=(0, 6))

        # Scheduled date label
        s = load_settings()
        dt = batch_post_datetime(s.get("post_time", "18:00"), idx)
        local_dt = dt.astimezone()
        date_str = local_dt.strftime("%b %-d")
        date_lbl = tk.Label(inner, text=date_str, font=(FONT_FAMILY, 8, "bold"),
                            fg=CRIMSON, bg=bg, width=7, anchor="center")
        date_lbl.grid(row=0, column=3, padx=(0, 6))

        # Remove button
        remove_btn = _make_lbtn(
            inner, "✕", lambda i=idx: self._batch_remove_row(i),
            bg=bg, fg=TEXT_DIM, hover_bg=bg, hover_fg=ERROR_RED, normal_fg=TEXT_DIM,
            font=(FONT_FAMILY, 11, "bold"), pady=2, padx=4
        )
        remove_btn.grid(row=0, column=4, padx=(4, 0))

        # Raw caption text area (full width, row 1) — editable before scheduling
        caption_text = tk.Text(inner, height=4, font=(FONT_FAMILY, 9),
                               fg=WHITE, bg=INPUT_BG, insertbackground=WHITE,
                               relief="flat", highlightthickness=1,
                               highlightbackground=BORDER, highlightcolor=CRIMSON,
                               wrap="word", padx=6, pady=6)
        caption_text.insert("1.0", caption or "⏳  Researching & writing caption…")
        caption_text.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 2))

        # Status label (shown after processing)
        status_lbl = tk.Label(inner, text="", font=(FONT_FAMILY, 8),
                              fg=LIGHT_GRAY, bg=bg, anchor="w")
        status_lbl.grid(row=2, column=0, columnspan=4, sticky="w")

        # Review button — opens the row so a Needs Review item can be
        # manually completed and approved for scheduling (issue #79).
        review_btn = _make_lbtn(
            inner, " EDIT ", lambda i=idx: self._open_batch_row_review(i),
            bg=bg, fg=TEXT_DIM, hover_bg=bg, hover_fg=WHITE, normal_fg=TEXT_DIM,
            font=(FONT_FAMILY, 8, "bold"), pady=2, padx=6
        )
        review_btn.grid(row=2, column=4, sticky="e")

        # Reason line — why this row needs review (metadata unavailable,
        # source verification pending, AI unavailable, Instagram blocked
        # metadata, etc.). Empty/hidden once the row is ready or approved.
        reason_lbl = tk.Label(inner, text="", font=(FONT_FAMILY, 8, "italic"),
                              fg=WARNING, bg=bg, anchor="w", wraplength=520, justify="left")
        reason_lbl.grid(row=3, column=0, columnspan=5, sticky="w")

        inner.columnconfigure(1, weight=1)

        row_data = {
            "path": path,
            "url": url,
            "final_caption": final_caption,
            "case_var": case_var,
            "caption_text": caption_text,
            "frame": frame,
            "status_lbl": status_lbl,
            "badge_lbl": badge_lbl,
            "date_lbl": date_lbl,
            "review_btn": review_btn,
            "reason_lbl": reason_lbl,
            "review_reason": "",
            "source_links": [url] if url else [],
            "notes": "",
            "proc_status": "ready" if caption else "queued",
            "idx": idx,
        }
        self._batch_rows.append(row_data)
        if caption:
            self._set_row_badge(row_data, "ready")

    def _batch_remove_row(self, original_idx):
        # Find by original idx (rows don't shift their stored idx)
        to_remove = self._batch_row_by_idx(original_idx)
        if to_remove:
            to_remove["frame"].destroy()
            self._batch_rows.remove(to_remove)
        self._refresh_batch_ui()
        self._refresh_batch_dates()

    def _batch_row_by_idx(self, original_idx):
        # Rows don't shift their stored idx when others are removed/reordered.
        return next((r for r in self._batch_rows if r["idx"] == original_idx), None)

    def _open_batch_row_review(self, original_idx):
        """Open/edit a batch row (issue #79): title, caption, source links
        and notes/facts are all editable here, with a clear "Approve for
        Scheduling" action once a Needs Review row has been manually
        completed. Never auto-publishes — approval only flips the row's
        status; Schedule All still has to be run separately."""
        row = self._batch_row_by_idx(original_idx)
        if row is None:
            return
        needs_review = row["proc_status"] == "needs_review"
        win, body = make_toplevel_shell(
            self, "REVIEW VIDEO" if needs_review else "EDIT VIDEO", width=620, height=660
        )

        if needs_review:
            reason = row.get("review_reason") or "manual verification recommended"
            reason_card = make_card(body, padx=12, pady=10, bg=WARNING_BG, border=WARNING, hover=False)
            reason_card.pack(fill="x", pady=(0, 12))
            tk.Label(
                card_body(reason_card), text=f"⚠  Needs review — {reason}",
                font=(FONT_FAMILY, 10, "bold"), fg=WARNING, bg=WARNING_BG,
                wraplength=560, justify="left", anchor="w",
            ).pack(fill="x")

        tk.Label(body, text="TITLE", font=(FONT_FAMILY, 9, "bold"),
                 fg=TEXT_SECONDARY, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        tk.Entry(
            body, textvariable=row["case_var"], font=(FONT_FAMILY, 10), fg=WHITE, bg=INPUT_BG,
            insertbackground=WHITE, relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=CRIMSON,
        ).pack(fill="x", pady=(0, 10))

        tk.Label(body, text="CAPTION  (generated fallback shown below — edit as needed)",
                 font=(FONT_FAMILY, 9, "bold"), fg=TEXT_SECONDARY, bg=BG, anchor="w"
                 ).pack(fill="x", pady=(0, 4))
        caption_box = tk.Text(
            body, height=8, font=(FONT_FAMILY, 10), fg=WHITE, bg=INPUT_BG, insertbackground=WHITE,
            relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=CRIMSON,
            wrap="word", padx=8, pady=8,
        )
        caption_box.insert("1.0", row["caption_text"].get("1.0", "end").strip())
        caption_box.pack(fill="both", expand=True, pady=(0, 10))

        tk.Label(body, text="SOURCE LINKS  (one per line)", font=(FONT_FAMILY, 9, "bold"),
                 fg=TEXT_SECONDARY, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        links_box = tk.Text(
            body, height=3, font=(FONT_FAMILY, 9), fg=WHITE, bg=INPUT_BG, insertbackground=WHITE,
            relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=CRIMSON,
            wrap="word", padx=8, pady=6,
        )
        existing_links = row.get("source_links", [])
        links_box.insert("1.0", "\n".join(existing_links))
        links_box.pack(fill="x", pady=(0, 10))

        tk.Label(body, text="NOTES / FACTS", font=(FONT_FAMILY, 9, "bold"),
                 fg=TEXT_SECONDARY, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        notes_box = tk.Text(
            body, height=4, font=(FONT_FAMILY, 9), fg=WHITE, bg=INPUT_BG, insertbackground=WHITE,
            relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=CRIMSON,
            wrap="word", padx=8, pady=6,
        )
        notes_box.insert("1.0", row.get("notes", ""))
        notes_box.pack(fill="x", pady=(0, 8))

        err_lbl = tk.Label(body, text="", font=(FONT_FAMILY, 9), fg=ERROR_RED, bg=BG,
                           anchor="w", wraplength=560, justify="left")
        err_lbl.pack(fill="x", pady=(0, 6))

        def _persist_edits():
            new_caption = caption_box.get("1.0", "end").strip()
            row["caption_text"].delete("1.0", "end")
            row["caption_text"].insert("1.0", new_caption)
            row["source_links"] = parse_pasted_urls(links_box.get("1.0", "end"))
            row["notes"] = notes_box.get("1.0", "end").strip()
            return new_caption

        def _save():
            _persist_edits()
            win.destroy()

        def _approve():
            new_caption = _persist_edits()
            if not row["case_var"].get().strip() or not new_caption:
                err_lbl.config(text="Title and caption are required before approving.")
                return
            row["review_reason"] = ""
            self._set_row_badge(row, "ready")
            self._set_row_status(row, "✓  Approved for scheduling", SUCCESS)
            win.destroy()

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x", pady=(4, 0))
        _make_lbtn(
            btn_row, "SAVE CHANGES", _save, bg=INPUT_BG, fg=WHITE, hover_bg=BORDER,
            font=(FONT_FAMILY, 10, "bold"), pady=10, padx=14,
        ).pack(side="left", padx=(0, 8))
        _make_lbtn(
            btn_row, "✓  APPROVE FOR SCHEDULING", _approve, bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=(FONT_FAMILY, 10, "bold"), pady=10, padx=14,
        ).pack(side="left", fill="x", expand=True)

        return win

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
            _lbtn_disable(self._btn_schedule_all, MUTED, TEXT_MUTED)
        else:
            self._batch_empty_lbl.pack_forget()
            self._btn_schedule_all.config(
                text=f"SCHEDULE ALL  ( {n} video{'s' if n != 1 else ''} )"
            )
            if not self._batch_running:
                _lbtn_enable(self._btn_schedule_all, CRIMSON, WHITE, CRIMSON_HOT)
            else:
                _lbtn_disable(self._btn_schedule_all, MUTED, TEXT_MUTED)

    # ── Batch processing ──────────────────────────────────────────────────────

    def _start_batch(self):
        if self._batch_running or not self._batch_rows:
            return
        # Don't let Schedule All race a still-running research/caption job —
        # the row's caption box may still hold the "researching…" placeholder.
        if any(row.get("proc_status") in ("queued", "working") for row in self._batch_rows):
            self._batch_status_lbl.config(
                text="⚠  Still researching & writing captions — wait for every video to finish "
                     "before scheduling.",
                fg=CRIMSON
            )
            return
        # Needs Review rows are never auto-published — each one has to be
        # opened, fixed, and approved before Schedule All will run (issue #79).
        needs_review_count = sum(1 for row in self._batch_rows if row.get("proc_status") == "needs_review")
        if needs_review_count:
            self._batch_status_lbl.config(
                text=f"⚠  {needs_review_count} video{'s' if needs_review_count != 1 else ''} still "
                     f"need manual review — open the row and click Approve for Scheduling first.",
                fg=CRIMSON
            )
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
                    text="⚠  yt-dlp is needed to download video URLs. Install it from Settings.",
                    fg=CRIMSON
                )
                return
        self._batch_running = True
        _lbtn_disable(self._btn_schedule_all, MUTED, TEXT_MUTED)
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
                set_row_status(f"✓  Saved as {output_path.name}", SUCCESS)
                continue

            # Step 2: caption. Add Videos rows already hold a reviewed, final
            # VerdictIn60-style caption (final_caption defaults True) — only
            # mechanically reformat if a caller explicitly opted out of that.
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
                    set_row_status(f"✅  Scheduled for {due_fmt}", SUCCESS)
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
            fg=SUCCESS
        ))
        self.after(0, self._refresh_batch_ui)

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
        tk.Frame(outer, bg=BORDER, height=1).pack(fill="x", padx=36, pady=(14, 0))

        footer_bar = tk.Frame(outer, bg=BG)
        footer_bar.pack(fill="x", padx=36, pady=(8, 16))

        self._lbl_buffer_status = tk.Label(
            footer_bar, text="", font=("Helvetica", 8), fg=MUTED, bg=BG, anchor="w"
        )
        self._lbl_buffer_status.pack(side="left", fill="x", expand=True)

        self._refresh_buffer_status()

    def _refresh_buffer_status(self):
        s = load_settings()
        has_buffer = bool(s.get("buffer_key") and s.get("buffer_channel_id"))
        post_time  = s.get("post_time", "18:00")
        if has_buffer:
            self._lbl_buffer_status.config(
                text=f"● Buffer ready  ·  posts at {post_time}", fg=SUCCESS
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


if __name__ == "__main__":
    app = App()
    app.mainloop()
