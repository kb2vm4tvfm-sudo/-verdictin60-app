import tkinter as tk
from tkinter import ttk

from verdictin60_ui.widgets import (
    BG, CRIMSON, CRIMSON_HOT, WHITE, MUTED, LIGHT_GRAY, _make_lbtn, _lbtn_disable,
)


def build_single_tab(app, parent):
    PAD = 36

    # ── Select file button ────────────────────────────────────────────────
    app._select_wrap = select_wrap = tk.Frame(parent, bg=BG)
    select_wrap.pack(padx=PAD, fill="x", pady=(22, 0))
    # 1px crimson border via Frame wrapper
    select_border = tk.Frame(select_wrap, bg=CRIMSON, padx=1, pady=1)
    select_border.pack(fill="x")
    app._btn_select = _make_lbtn(
        select_border, "▶   SELECT CASE FILE", app._pick_file,
        bg="#182236", fg=WHITE, hover_bg="#232c40",
        font=("Helvetica", 13, "bold"), pady=16, padx=22, anchor="w"
    )
    app._btn_select.pack(fill="x")
    tk.Frame(select_wrap, bg=CRIMSON, width=4).place(x=0, y=0, relheight=1.0)

    # ── File card (hidden until chosen) ───────────────────────────────────
    app._card_frame = tk.Frame(parent, bg=BG)
    card_inner = tk.Frame(app._card_frame, bg="#182236",
                          highlightbackground="#232c40", highlightthickness=1)
    card_inner.pack(fill="x", padx=PAD, pady=(12, 0))
    tk.Frame(card_inner, bg=CRIMSON, height=2).pack(fill="x")
    card_body = tk.Frame(card_inner, bg="#182236")
    card_body.pack(fill="x", padx=16, pady=12)
    tk.Label(card_body, text="▶", font=("Helvetica", 18, "bold"),
             fg=CRIMSON, bg="#182236").grid(row=0, column=0, rowspan=2, padx=(0, 14))
    app._lbl_filename = tk.Label(card_body, text="",
                                  font=("Helvetica", 12, "bold"),
                                  fg=WHITE, bg="#182236", anchor="w")
    app._lbl_filename.grid(row=0, column=1, sticky="w")
    tk.Label(card_body, text="READY FOR PROCESSING",
             font=("Helvetica", 8, "bold"), fg=CRIMSON,
             bg="#182236", anchor="w").grid(row=1, column=1, sticky="w")
    card_body.columnconfigure(1, weight=1)

    # ── Case Title ────────────────────────────────────────────────────────
    title_frame = tk.Frame(parent, bg=BG)
    title_frame.pack(padx=PAD, fill="x", pady=(16, 0))
    tk.Label(title_frame, text="CASE TITLE", font=("Helvetica", 8, "bold"),
             fg="#a8b3c7", bg=BG).pack(anchor="w")
    app._title_entry = tk.Entry(title_frame, textvariable=tk.StringVar(),
             font=("Helvetica", 11), fg=WHITE, bg="#182236",
             insertbackground=WHITE, relief="flat",
             highlightthickness=1, highlightbackground="#232c40",
             highlightcolor=CRIMSON)
    app._title_var = app._title_entry["textvariable"] = tk.StringVar()
    app._title_entry.config(textvariable=app._title_var)
    app._title_entry.pack(fill="x", ipady=8, pady=(6, 0))

    # ── Raw Caption ───────────────────────────────────────────────────────
    caption_frame = tk.Frame(parent, bg=BG)
    caption_frame.pack(padx=PAD, fill="x", pady=(14, 0))
    tk.Label(caption_frame, text="RAW CAPTION", font=("Helvetica", 8, "bold"),
             fg="#a8b3c7", bg=BG).pack(anchor="w")
    app._caption_text = tk.Text(
        caption_frame, height=8, font=("Helvetica", 10),
        fg=WHITE, bg="#182236", insertbackground=WHITE,
        relief="flat", highlightthickness=1, highlightbackground="#232c40",
        highlightcolor=CRIMSON, wrap="word", padx=8, pady=8
    )
    app._caption_text.pack(fill="x", pady=(6, 0))

    # ── Export button ─────────────────────────────────────────────────────
    export_wrap = tk.Frame(parent, bg=BG)
    export_wrap.pack(padx=PAD, fill="x", pady=(20, 0))
    app._btn_export = _make_lbtn(
        export_wrap, "EXPORT FINISHED REEL", app._start_export,
        bg=MUTED, fg="#94a3b8", hover_bg=CRIMSON_HOT, hover_fg=WHITE,
        normal_fg="#94a3b8", font=("Helvetica", 13, "bold"), pady=16, padx=20
    )
    _lbtn_disable(app._btn_export, MUTED, "#94a3b8")
    app._btn_export.pack(fill="x")

    # ── Case file animation canvas ────────────────────────────────────────
    app._anim_canvas = tk.Canvas(
        parent, bg="#101625", height=170,
        highlightthickness=1, highlightbackground="#232c40"
    )
    app._anim_canvas.pack(padx=PAD, fill="x", pady=(18, 0))
    app._anim_canvas.bind("<Configure>", lambda e: app._anim_render())

    # Hidden progress/dot/status kept for compat with existing logic
    app._progress = ttk.Progressbar(parent, orient="horizontal", mode="indeterminate")
    app._dot = tk.Label(parent, text="●", fg=BG, bg=BG)
    app._lbl_status = tk.Label(parent, text="", fg=LIGHT_GRAY, bg=BG)

    # Animation state
    app._anim_state   = "idle"   # idle | processing | scheduling | success | error
    app._anim_phase   = 0.0      # 0.0–1.0 within the current state
    app._anim_status  = ""
    app._anim_tick_id = None
    app.after(60, app._anim_render)

    # ── Open folder button ────────────────────────────────────────────────
    app._btn_open = _make_lbtn(
        parent, "▶   OPEN OUTPUT FOLDER", app._open_output_folder,
        bg="#232c40", fg="#a8b3c7", hover_bg="#333e58", hover_fg=WHITE,
        normal_fg="#a8b3c7", font=("Helvetica", 10, "bold"), pady=10, padx=20
    )
