import tkinter as tk

from verdictin60_ui.widgets import (
    BG, CRIMSON, CRIMSON_HOT, WHITE, MUTED, LIGHT_GRAY, _make_lbtn, _lbtn_disable,
)


def build_batch_tab(app, parent):
    PAD = 36

    # ── Quick publish latest ───────────────────────────────────────────────
    quick_border = tk.Frame(parent, bg=CRIMSON, padx=1, pady=1)
    quick_border.pack(padx=PAD, fill="x", pady=(22, 0))
    btn_quick = _make_lbtn(
        quick_border, "⚡   PUBLISH LATEST CASE", app._quick_publish_latest,
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
        add_border, "▶   ADD VIDEOS", app._batch_add_files,
        bg="#1a1a1a", fg=WHITE, hover_bg="#2a2a2a",
        font=("Helvetica", 13, "bold"), pady=16, padx=22, anchor="w"
    )
    btn_add.pack(fill="x")
    docx_border = tk.Frame(add_wrap, bg="#2a2a2a", padx=1, pady=1)
    docx_border.pack(side="left", fill="x", expand=True)
    btn_docx = _make_lbtn(
        docx_border, "IMPORT DOCX QUEUE", app._batch_import_docx,
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

    app._batch_canvas = tk.Canvas(list_outer, bg="#0d0d0d", highlightthickness=0)
    scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                             command=app._batch_canvas.yview,
                             bg="#1a1a1a", troughcolor="#0d0d0d",
                             activebackground=CRIMSON)
    app._batch_canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    app._batch_canvas.pack(side="left", fill="both", expand=True)

    app._batch_list_frame = tk.Frame(app._batch_canvas, bg="#0d0d0d")
    app._batch_canvas_window = app._batch_canvas.create_window(
        (0, 0), window=app._batch_list_frame, anchor="nw"
    )
    app._batch_list_frame.bind("<Configure>", app._on_batch_list_resize)
    app._batch_canvas.bind("<Configure>", app._on_batch_canvas_resize)

    # Empty state
    app._batch_empty_lbl = tk.Label(
        app._batch_list_frame,
        text="No videos added yet.\nAdd videos or import a DOCX queue to get started.",
        font=("Helvetica", 10), fg="#555555", bg="#0d0d0d", justify="center"
    )
    app._batch_empty_lbl.pack(pady=40)

    # ── Schedule All button ───────────────────────────────────────────────
    sched_wrap = tk.Frame(parent, bg=BG)
    sched_wrap.pack(padx=PAD, fill="x", pady=(14, 0))
    app._btn_schedule_all = _make_lbtn(
        sched_wrap, "SCHEDULE ALL  ( 0 videos )", app._start_batch,
        bg=MUTED, fg="#888888", hover_bg=CRIMSON_HOT, hover_fg=WHITE,
        normal_fg="#888888", font=("Helvetica", 13, "bold"), pady=16, padx=20
    )
    _lbtn_disable(app._btn_schedule_all, MUTED, "#888888")
    app._btn_schedule_all.pack(fill="x")

    # ── Batch status ──────────────────────────────────────────────────────
    status_bar = tk.Frame(parent, bg="#0d0d0d")
    status_bar.pack(padx=PAD, fill="x", pady=(10, 0))
    app._batch_status_lbl = tk.Label(
        status_bar, text="", font=("Courier", 9),
        fg=LIGHT_GRAY, bg="#0d0d0d", wraplength=600, justify="left", anchor="w"
    )
    app._batch_status_lbl.pack(fill="x", padx=12, pady=8)
