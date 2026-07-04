import tkinter as tk
from tkinter import ttk

from verdictin60_ui.theme import (
    BG, CARD, INPUT_BG, BORDER, BORDER_LIGHT,
    TEXT, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, ACCENT_HOT, DISABLED,
    FONT_FAMILY,
)
from verdictin60_ui.components import make_card, card_body, make_badge
from verdictin60_ui.widgets import _make_lbtn, _lbtn_disable

PAD = 36


def _field_label(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_SECONDARY,
                     font=(FONT_FAMILY, 8, "bold"))


def build_single_tab(app, parent):
    # ── Select file button ────────────────────────────────────────────────
    app._select_wrap = select_wrap = tk.Frame(parent, bg=BG)
    select_wrap.pack(padx=PAD, fill="x", pady=(22, 0))
    # 1px crimson border via Frame wrapper
    select_border = tk.Frame(select_wrap, bg=ACCENT, padx=1, pady=1)
    select_border.pack(fill="x")
    app._btn_select = _make_lbtn(
        select_border, "▶   SELECT CASE FILE", app._pick_file,
        bg=INPUT_BG, fg=TEXT, hover_bg=BORDER,
        font=(FONT_FAMILY, 13, "bold"), pady=16, padx=22, anchor="w"
    )
    app._btn_select.pack(fill="x")
    tk.Frame(select_wrap, bg=ACCENT, width=4).place(x=0, y=0, relheight=1.0)

    # ── File card (hidden until chosen) ───────────────────────────────────
    app._card_frame = tk.Frame(parent, bg=BG)
    file_card = make_card(app._card_frame, padx=16, pady=12, bg=INPUT_BG, hover=False)
    file_card.pack(fill="x", padx=PAD, pady=(12, 0))
    tk.Frame(file_card, bg=ACCENT, height=2).pack(fill="x", before=card_body(file_card))
    body = card_body(file_card)
    tk.Label(body, text="▶", font=(FONT_FAMILY, 18, "bold"),
             fg=ACCENT, bg=INPUT_BG).grid(row=0, column=0, rowspan=2, padx=(0, 14))
    app._lbl_filename = tk.Label(body, text="",
                                  font=(FONT_FAMILY, 12, "bold"),
                                  fg=TEXT, bg=INPUT_BG, anchor="w")
    app._lbl_filename.grid(row=0, column=1, sticky="w")
    make_badge(body, "READY FOR PROCESSING", status="success").grid(
        row=1, column=1, sticky="w", pady=(4, 0))
    body.columnconfigure(1, weight=1)

    # ── Case Title ────────────────────────────────────────────────────────
    title_frame = tk.Frame(parent, bg=BG)
    title_frame.pack(padx=PAD, fill="x", pady=(16, 0))
    _field_label(title_frame, "CASE TITLE").pack(anchor="w")
    app._title_var = tk.StringVar()
    app._title_entry = tk.Entry(
        title_frame, textvariable=app._title_var,
        font=(FONT_FAMILY, 11), fg=TEXT, bg=INPUT_BG,
        insertbackground=TEXT, relief="flat",
        highlightthickness=1, highlightbackground=BORDER,
        highlightcolor=ACCENT,
    )
    app._title_entry.pack(fill="x", ipady=8, pady=(6, 0))

    # ── Raw Caption ───────────────────────────────────────────────────────
    caption_frame = tk.Frame(parent, bg=BG)
    caption_frame.pack(padx=PAD, fill="x", pady=(14, 0))
    _field_label(caption_frame, "RAW CAPTION").pack(anchor="w")
    app._caption_text = tk.Text(
        caption_frame, height=8, font=(FONT_FAMILY, 10),
        fg=TEXT, bg=INPUT_BG, insertbackground=TEXT,
        relief="flat", highlightthickness=1, highlightbackground=BORDER,
        highlightcolor=ACCENT, wrap="word", padx=8, pady=8
    )
    app._caption_text.pack(fill="x", pady=(6, 0))

    # ── Export button ─────────────────────────────────────────────────────
    export_wrap = tk.Frame(parent, bg=BG)
    export_wrap.pack(padx=PAD, fill="x", pady=(20, 0))
    app._btn_export = _make_lbtn(
        export_wrap, "EXPORT FINISHED REEL", app._start_export,
        bg=DISABLED, fg=TEXT_MUTED, hover_bg=ACCENT_HOT, hover_fg=TEXT,
        normal_fg=TEXT_MUTED, font=(FONT_FAMILY, 13, "bold"), pady=16, padx=20
    )
    _lbtn_disable(app._btn_export, DISABLED, TEXT_MUTED)
    app._btn_export.pack(fill="x")

    # ── Case file animation canvas ────────────────────────────────────────
    # Kept as a plain bordered Canvas rather than make_card: app.py's
    # _draw_anim() dynamically flashes this canvas's own highlightthickness/
    # highlightbackground on a successful export, so it must own its border
    # rather than nesting inside a second bordered frame.
    _field_label(parent, "EXPORT STATUS").pack(anchor="w", padx=PAD, pady=(18, 6))
    app._anim_canvas = tk.Canvas(
        parent, bg=CARD, height=170,
        highlightthickness=1, highlightbackground=BORDER
    )
    app._anim_canvas.pack(padx=PAD, fill="x")
    app._anim_canvas.bind("<Configure>", lambda e: app._anim_render())

    # Hidden progress/dot/status kept for compat with existing logic
    app._progress = ttk.Progressbar(parent, orient="horizontal", mode="indeterminate")
    app._dot = tk.Label(parent, text="●", fg=BG, bg=BG)
    app._lbl_status = tk.Label(parent, text="", fg=TEXT_MUTED, bg=BG)

    # Animation state
    app._anim_state   = "idle"   # idle | processing | scheduling | success | error
    app._anim_phase   = 0.0      # 0.0–1.0 within the current state
    app._anim_status  = ""
    app._anim_tick_id = None
    app.after(60, app._anim_render)

    # ── Open folder button ────────────────────────────────────────────────
    app._btn_open = _make_lbtn(
        parent, "▶   OPEN OUTPUT FOLDER", app._open_output_folder,
        bg=BORDER, fg=TEXT_SECONDARY, hover_bg=BORDER_LIGHT, hover_fg=TEXT,
        normal_fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10, "bold"), pady=10, padx=20
    )
