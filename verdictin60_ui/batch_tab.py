import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from verdictin60_ui.theme import (
    BG, CARD, BORDER,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, DISABLED, INPUT_BG, ERROR,
    ACCENT, ACCENT_HOT, FONT_FAMILY, FONT_MONO,
)
from verdictin60_ui.components import make_card, card_body, make_empty_state, make_toplevel_shell
from verdictin60_ui.widgets import _make_lbtn, _lbtn_disable
from verdictin60_core.batch_items import parse_pasted_urls, parse_url_list_file

PAD = 36


def build_batch_tab(app, parent):
    # ── Add videos — the single primary action ──────────────────────────────
    add_border = tk.Frame(parent, bg=ACCENT, padx=1, pady=1)
    add_border.pack(padx=PAD, fill="x", pady=(22, 0))
    btn_add = _make_lbtn(
        add_border, "▶   ADD VIDEOS", lambda: open_add_videos_dialog(app),
        bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT,
        font=(FONT_FAMILY, 14, "bold"), pady=18, padx=22, anchor="w"
    )
    btn_add.pack(fill="x")

    # ── Column headers ────────────────────────────────────────────────────
    hdr = tk.Frame(parent, bg=CARD)
    hdr.pack(padx=PAD, fill="x", pady=(16, 0))
    for txt, w in [("SOURCE", 150), ("CASE TITLE", 190), ("STATUS", 90), ("DATE", 72), ("", 24)]:
        tk.Label(hdr, text=txt, font=(FONT_FAMILY, 7, "bold"),
                 fg=TEXT_SECONDARY, bg=CARD, width=w // 7, anchor="w").pack(side="left", padx=6)

    # ── Selected / queued items panel ──────────────────────────────────────
    list_card = make_card(parent, padx=0, pady=0, bg=CARD, border=BORDER, hover=False)
    list_card.pack(padx=PAD, fill="both", expand=True, pady=(0, 0))
    list_outer = card_body(list_card)

    app._batch_canvas = tk.Canvas(list_outer, bg=CARD, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                             command=app._batch_canvas.yview,
                             bg=INPUT_BG, troughcolor=CARD,
                             activebackground=ACCENT)
    app._batch_canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    app._batch_canvas.pack(side="left", fill="both", expand=True)

    app._batch_list_frame = tk.Frame(app._batch_canvas, bg=CARD)
    app._batch_canvas_window = app._batch_canvas.create_window(
        (0, 0), window=app._batch_list_frame, anchor="nw"
    )
    app._batch_list_frame.bind("<Configure>", app._on_batch_list_resize)
    app._batch_canvas.bind("<Configure>", app._on_batch_canvas_resize)

    # Empty state
    app._batch_empty_lbl = make_empty_state(
        app._batch_list_frame,
        "No videos added yet.\nClick Add Videos to paste URLs, import a URL list, "
        "or select local video files.",
        bg=CARD,
    )
    app._batch_empty_lbl.pack(pady=40)

    # ── Schedule All button ───────────────────────────────────────────────
    sched_wrap = tk.Frame(parent, bg=BG)
    sched_wrap.pack(padx=PAD, fill="x", pady=(14, 0))
    app._btn_schedule_all = _make_lbtn(
        sched_wrap, "SCHEDULE ALL  ( 0 videos )", app._start_batch,
        bg=DISABLED, fg=TEXT_MUTED, hover_bg=ACCENT_HOT, hover_fg=TEXT,
        normal_fg=TEXT_MUTED, font=(FONT_FAMILY, 13, "bold"), pady=16, padx=20
    )
    _lbtn_disable(app._btn_schedule_all, DISABLED, TEXT_MUTED)
    app._btn_schedule_all.pack(fill="x")

    # ── Batch status ──────────────────────────────────────────────────────
    status_card = make_card(parent, padx=12, pady=8, bg=CARD, border=BORDER, hover=False)
    status_card.pack(padx=PAD, fill="x", pady=(10, 0))
    app._batch_status_lbl = tk.Label(
        card_body(status_card), text="", font=(FONT_MONO, 9),
        fg=TEXT_MUTED, bg=CARD, wraplength=600, justify="left", anchor="w"
    )
    app._batch_status_lbl.pack(fill="x")


def open_add_videos_dialog(app):
    """The single Add Videos workflow: paste multiple URLs, import a .txt/.csv
    URL list, and/or select local video files — all in one place (issue #77)."""
    win, body = make_toplevel_shell(app, "ADD VIDEOS", width=640, height=580)

    tk.Label(body, text="PASTE VIDEO URLS  (one per line)", font=(FONT_FAMILY, 9, "bold"),
             fg=TEXT_SECONDARY, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

    url_text = tk.Text(
        body, height=9, font=(FONT_FAMILY, 10), fg=TEXT, bg=INPUT_BG,
        insertbackground=TEXT, relief="flat", highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=ACCENT, wrap="word", padx=8, pady=8,
    )
    url_text.pack(fill="both", expand=True, pady=(0, 10))

    status_lbl = tk.Label(
        body, text="", font=(FONT_FAMILY, 9), fg=TEXT_SECONDARY, bg=BG,
        anchor="w", wraplength=580, justify="left",
    )

    btn_row = tk.Frame(body, bg=BG)
    btn_row.pack(fill="x", pady=(0, 6))

    def _import_url_list():
        path = filedialog.askopenfilename(
            title="Import URL list",
            filetypes=[("Text/CSV", "*.txt *.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            urls = parse_url_list_file(Path(path))
        except Exception as e:
            status_lbl.config(text=f"Could not read list: {e}", fg=ERROR)
            return
        if not urls:
            status_lbl.config(text=f"No URLs found in {Path(path).name}.", fg=ERROR)
            return
        existing = url_text.get("1.0", "end").strip()
        url_text.insert("end", ("\n" if existing else "") + "\n".join(urls))
        status_lbl.config(
            text=f"Imported {len(urls)} URL{'s' if len(urls) != 1 else ''} from {Path(path).name}.",
            fg=TEXT_SECONDARY,
        )

    _make_lbtn(
        btn_row, "IMPORT .TXT / .CSV", _import_url_list,
        bg=INPUT_BG, fg=TEXT, hover_bg=BORDER,
        font=(FONT_FAMILY, 10, "bold"), pady=10, padx=14,
    ).pack(side="left", padx=(0, 8))

    picked_files = []
    files_lbl = tk.Label(
        body, text="No local video files selected.", font=(FONT_FAMILY, 9),
        fg=TEXT_MUTED, bg=BG, anchor="w", wraplength=580, justify="left",
    )

    def _pick_local_files():
        paths = filedialog.askopenfilenames(
            title="Select case videos",
            filetypes=[("Video files", "*.mp4 *.mov"), ("All files", "*.*")],
        )
        for p in paths:
            if p not in picked_files:
                picked_files.append(p)
        if picked_files:
            names = ", ".join(Path(p).name for p in picked_files[:4])
            more = f" (+{len(picked_files) - 4} more)" if len(picked_files) > 4 else ""
            files_lbl.config(
                text=f"{len(picked_files)} file(s) selected: {names}{more}", fg=TEXT_SECONDARY
            )

    _make_lbtn(
        btn_row, "SELECT LOCAL VIDEO FILES", _pick_local_files,
        bg=INPUT_BG, fg=TEXT, hover_bg=BORDER,
        font=(FONT_FAMILY, 10, "bold"), pady=10, padx=14,
    ).pack(side="left")

    files_lbl.pack(fill="x", pady=(0, 10))
    status_lbl.pack(fill="x", pady=(0, 10))

    def _confirm():
        urls = parse_pasted_urls(url_text.get("1.0", "end"))
        paths = [Path(p) for p in picked_files]
        if not urls and not paths:
            status_lbl.config(text="Paste at least one URL or select a local video file.", fg=ERROR)
            return
        win.destroy()
        app._batch_add_items(urls, paths)

    confirm_border = tk.Frame(body, bg=ACCENT, padx=1, pady=1)
    confirm_border.pack(fill="x", side="bottom")
    _make_lbtn(
        confirm_border, "▶   ADD TO QUEUE", _confirm,
        bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT,
        font=(FONT_FAMILY, 12, "bold"), pady=14, padx=18,
    ).pack(fill="x")

    return win
