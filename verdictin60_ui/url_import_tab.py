import tkinter as tk
from tkinter import ttk

from verdictin60_ui.theme import (
    BG, CARD, CARD_ALT, BORDER, TEXT, TEXT_MUTED,
    ACCENT, ACCENT_HOT, INPUT_BG, DISABLED, SUCCESS, SUCCESS_BG,
    FONT_FAMILY, FONT_MONO, SPACE_XS, SPACE_SM, SPACE_LG,
)
from verdictin60_ui.components import (
    make_card, card_body, make_badge, make_loading_state, make_error_banner,
)
from verdictin60_ui.widgets import _make_lbtn

# Must match the padx used when app.py re-packs _btn_retry_schedule after a
# failed Archive.org poll (see App._url_retry_schedule), since that call packs
# straight into `inner` rather than through a helper here.
PAD = 30


def _field_label(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_MUTED,
                     font=(FONT_FAMILY, 10, "bold"))


def _bordered_entry(parent, **kwargs):
    return tk.Entry(
        parent, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, bd=0, relief="flat",
        highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        **kwargs,
    )


def build_url_tab(app, parent):
    scroll_outer = tk.Frame(parent, bg=BG)
    scroll_outer.pack(fill="both", expand=True)
    canvas_scroll = tk.Canvas(scroll_outer, bg=BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(scroll_outer, orient="vertical",
                              command=canvas_scroll.yview)
    canvas_scroll.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas_scroll.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas_scroll, bg=BG)
    inner_win = canvas_scroll.create_window((0, 0), window=inner, anchor="nw")

    def _on_resize(e):
        canvas_scroll.itemconfig(inner_win, width=e.width)
    def _on_inner_configure(e):
        canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
    canvas_scroll.bind("<Configure>", _on_resize)
    inner.bind("<Configure>", _on_inner_configure)

    # ── Ollama status card ─────────────────────────────────────────────────
    ollama_card = make_card(inner, padx=14, pady=10, hover=False)
    ollama_card.pack(fill="x", padx=PAD, pady=(SPACE_LG - 6, 0))
    ollama_row = tk.Frame(card_body(ollama_card), bg=CARD)
    ollama_row.pack(fill="x")

    app._ollama_loading = make_loading_state(ollama_row, "Checking Ollama…", bg=CARD)
    app._ollama_loading.pack(side="left")
    app._ollama_dot, app._ollama_status_lbl = app._ollama_loading.winfo_children()

    app._btn_install_ollama = _make_lbtn(
        ollama_row, "Install Ollama", app._url_install_ollama,
        bg=CARD_ALT, fg=TEXT_MUTED, hover_bg=BORDER, hover_fg=TEXT,
        font=(FONT_FAMILY, 9), pady=4, padx=10
    )
    # packed/hidden dynamically by _url_check_ollama_status

    # ── URL input ─────────────────────────────────────────────────────────
    _field_label(inner, "PASTE VIDEO URL").pack(anchor="w", padx=PAD, pady=(SPACE_LG, SPACE_XS))
    app._url_entry = _bordered_entry(inner, font=(FONT_MONO, 13))
    app._url_entry.pack(fill="x", padx=PAD, ipady=10)
    app._url_entry.insert(0, "https://")
    app._url_entry.bind("<FocusIn>", app._url_entry_focus)

    # ── Platform buttons (cosmetic) ───────────────────────────────────────
    plat_frame = tk.Frame(inner, bg=BG)
    plat_frame.pack(padx=PAD, pady=(SPACE_SM + 2, 0), anchor="w")
    app._url_plat_btns = {}
    for plat in ("TikTok", "Instagram", "YouTube"):
        btn = tk.Label(plat_frame, text=plat, bg=INPUT_BG, fg=DISABLED,
                       font=(FONT_FAMILY, 10, "bold"), padx=14, pady=6,
                       cursor="hand2", highlightthickness=0)
        btn.pack(side="left", padx=(0, 6))
        app._url_plat_btns[plat] = btn
    app._url_entry.bind("<KeyRelease>", lambda e: app._url_detect_platform())

    # ── Case title ────────────────────────────────────────────────────────
    title_row = tk.Frame(inner, bg=BG)
    title_row.pack(fill="x", padx=PAD, pady=(SPACE_LG, SPACE_XS))
    _field_label(title_row, "CASE TITLE").pack(side="left")
    app._url_ai_badge = make_badge(title_row, "✦ AI will auto-detect", status="neutral")
    app._url_ai_badge.pack(side="left", padx=(SPACE_SM, 0))
    app._url_title_entry = _bordered_entry(inner, font=(FONT_FAMILY, 13))
    app._url_title_entry.pack(fill="x", padx=PAD, ipady=10)

    # ── Buffer caption ────────────────────────────────────────────────────
    cap_row = tk.Frame(inner, bg=BG)
    cap_row.pack(fill="x", padx=PAD, pady=(SPACE_LG, SPACE_XS))
    _field_label(cap_row, "BUFFER CAPTION").pack(side="left")
    app._url_cap_badge = make_badge(cap_row, "✦ AI will generate", status="neutral")
    app._url_cap_badge.pack(side="left", padx=(SPACE_SM, 0))
    cap_frame = tk.Frame(inner, bg=INPUT_BG,
                         highlightthickness=1, highlightbackground=BORDER)
    cap_frame.pack(fill="x", padx=PAD)
    app._url_caption_text = tk.Text(cap_frame, bg=INPUT_BG, fg=TEXT,
                                     insertbackground=TEXT, font=(FONT_FAMILY, 12),
                                     bd=0, relief="flat", highlightthickness=0,
                                     wrap="word", height=7)
    app._url_caption_text.pack(fill="x", padx=10, pady=10)

    app._btn_use_my_caption = _make_lbtn(
        inner, "USE THIS CAPTION", app._start_url_use_my_caption,
        bg=INPUT_BG, fg=TEXT_MUTED, hover_bg=BORDER, hover_fg=TEXT,
        font=(FONT_FAMILY, 10, "bold"), pady=9, padx=16
    )
    app._btn_use_my_caption.pack(padx=PAD, fill="x", pady=(SPACE_SM, 0))

    # ── Import & Schedule button ──────────────────────────────────────────
    app._btn_url_import = _make_lbtn(
        inner, "IMPORT & SCHEDULE", app._start_url_import,
        bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT,
        font=(FONT_FAMILY, 14, "bold"), pady=16
    )
    app._btn_url_import.pack(padx=PAD, pady=(SPACE_LG - 4, 0), fill="x")

    # ── Error banner (hidden until _url_set_status(..., error=True)) ──────
    app._url_error_host = tk.Frame(inner, bg=BG)
    app._url_error_host.pack(fill="x", padx=PAD)

    def _url_show_error(message):
        for child in app._url_error_host.winfo_children():
            child.destroy()
        banner = make_error_banner(app._url_error_host, message, title="Import error")
        banner.pack(fill="x", pady=(SPACE_SM, 0))
    app._url_show_error = _url_show_error

    def _url_hide_error():
        for child in app._url_error_host.winfo_children():
            child.destroy()
    app._url_hide_error = _url_hide_error

    # ── Status / progress area (case-file + gavel animation) ──────────────
    # Kept as a plain bordered Canvas rather than make_card: app.py's
    # _draw_anim() dynamically flashes this canvas's own highlightthickness/
    # highlightbackground on a successful import, so it must own its border
    # rather than nesting inside a second bordered frame.
    _field_label(inner, "IMPORT STATUS").pack(anchor="w", padx=PAD, pady=(SPACE_LG - 6, SPACE_XS))
    app._url_anim_canvas = tk.Canvas(
        inner, bg=CARD, height=170,
        highlightthickness=1, highlightbackground=BORDER,
    )
    app._url_anim_canvas.pack(padx=PAD, fill="x", pady=(0, SPACE_LG - 4))
    app._url_anim_canvas.bind("<Configure>", lambda e: app._url_anim_render())

    app._url_anim_state   = "idle"
    app._url_anim_phase   = 0.0
    app._url_anim_status  = ""
    app._url_anim_tick_id = None
    app.after(60, app._url_anim_render)

    # ── Retry & Schedule button (hidden until Archive.org poll exhausted) ──
    app._btn_retry_schedule = _make_lbtn(
        inner, "↻  RETRY & SCHEDULE", app._url_retry_schedule,
        bg=SUCCESS_BG, fg=SUCCESS, hover_bg="#1a4a34", hover_fg=TEXT,
        font=(FONT_FAMILY, 12, "bold"), pady=12
    )
    # Packed/hidden dynamically — stays hidden until UploadPendingError

    # Check Ollama status after UI is built
    app.after(200, app._url_check_ollama_status)
