import tkinter as tk

from verdictin60_ui.theme import (
    BG, CARD, BORDER,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, DISABLED, INPUT_BG,
    ACCENT, ACCENT_HOT, FONT_FAMILY, FONT_MONO,
)
from verdictin60_ui.components import make_card, card_body, make_empty_state
from verdictin60_ui.widgets import _make_lbtn, _lbtn_disable

PAD = 36


def build_batch_tab(app, parent):
    # ── Quick publish latest ───────────────────────────────────────────────
    quick_border = tk.Frame(parent, bg=ACCENT, padx=1, pady=1)
    quick_border.pack(padx=PAD, fill="x", pady=(22, 0))
    btn_quick = _make_lbtn(
        quick_border, "⚡   PUBLISH LATEST CASE", app._quick_publish_latest,
        bg="#271512", fg=ACCENT, hover_bg=ACCENT, hover_fg=TEXT,
        font=(FONT_FAMILY, 14, "bold"), pady=18, padx=22, anchor="w"
    )
    btn_quick.pack(fill="x")

    # ── Add videos / DOCX queue buttons ───────────────────────────────────
    add_wrap = tk.Frame(parent, bg=BG)
    add_wrap.pack(padx=PAD, fill="x", pady=(10, 0))
    add_border = tk.Frame(add_wrap, bg=ACCENT, padx=1, pady=1)
    add_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
    btn_add = _make_lbtn(
        add_border, "▶   ADD VIDEOS", app._batch_add_files,
        bg=INPUT_BG, fg=TEXT, hover_bg=BORDER,
        font=(FONT_FAMILY, 13, "bold"), pady=16, padx=22, anchor="w"
    )
    btn_add.pack(fill="x")
    docx_border = tk.Frame(add_wrap, bg=BORDER, padx=1, pady=1)
    docx_border.pack(side="left", fill="x", expand=True)
    btn_docx = _make_lbtn(
        docx_border, "IMPORT DOCX QUEUE", app._batch_import_docx,
        bg=INPUT_BG, fg=TEXT, hover_bg=BORDER,
        font=(FONT_FAMILY, 13, "bold"), pady=16, padx=22, anchor="w"
    )
    btn_docx.pack(fill="x")

    # ── Column headers ────────────────────────────────────────────────────
    hdr = tk.Frame(parent, bg=CARD)
    hdr.pack(padx=PAD, fill="x", pady=(16, 0))
    for txt, w in [("SOURCE", 160), ("CASE TITLE", 200), ("DATE", 72), ("", 24)]:
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
        "No videos added yet.\nAdd videos or import a DOCX queue to get started.",
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
