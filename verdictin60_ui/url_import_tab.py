import tkinter as tk
from tkinter import ttk

from verdictin60_ui.widgets import BG, CRIMSON, CRIMSON_HOT, WHITE, LIGHT_GRAY, _make_lbtn


def build_url_tab(app, parent):
    PAD = 30
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

    # ── Ollama status bar ─────────────────────────────────────────────────
    ollama_bar = tk.Frame(inner, bg="#1a1715",
                          highlightthickness=1, highlightbackground="#2a2725")
    ollama_bar.pack(fill="x", padx=PAD, pady=(18, 0))
    ollama_inner = tk.Frame(ollama_bar, bg="#1a1715")
    ollama_inner.pack(fill="x", padx=12, pady=8)
    app._ollama_dot = tk.Label(ollama_inner, text="●", bg="#1a1715",
                                fg="#5c5850", font=("Helvetica", 10))
    app._ollama_dot.pack(side="left")
    app._ollama_status_lbl = tk.Label(
        ollama_inner, text="Checking Ollama...", bg="#1a1715",
        fg=LIGHT_GRAY, font=("Helvetica", 10)
    )
    app._ollama_status_lbl.pack(side="left", padx=(6, 0))
    app._btn_install_ollama = _make_lbtn(
        ollama_inner, "Install Ollama", app._url_install_ollama,
        bg="#1f1b18", fg=LIGHT_GRAY, hover_bg="#2a2725",
        font=("Helvetica", 9), pady=4, padx=10
    )
    # packed/hidden dynamically by _url_check_ollama_status

    # ── URL input ─────────────────────────────────────────────────────────
    tk.Label(inner, text="PASTE VIDEO URL", bg=BG, fg=LIGHT_GRAY,
             font=("Helvetica", 10, "bold")).pack(anchor="w", padx=PAD, pady=(18, 4))
    url_frame = tk.Frame(inner, bg="#1f1b18",
                         highlightthickness=1, highlightbackground="#332f2c")
    url_frame.pack(fill="x", padx=PAD)
    app._url_entry = tk.Entry(url_frame, bg="#1f1b18", fg=WHITE, insertbackground=WHITE,
                               font=("Courier", 13), bd=0, relief="flat",
                               highlightthickness=0)
    app._url_entry.pack(fill="x", padx=10, pady=10)
    app._url_entry.insert(0, "https://")
    app._url_entry.bind("<FocusIn>", app._url_entry_focus)

    # ── Platform buttons (cosmetic) ───────────────────────────────────────
    plat_frame = tk.Frame(inner, bg=BG)
    plat_frame.pack(padx=PAD, pady=(10, 0), anchor="w")
    app._url_plat_btns = {}
    for plat in ("TikTok", "Instagram", "YouTube"):
        btn = tk.Label(plat_frame, text=plat, bg="#1f1b18", fg="#6b675f",
                       font=("Helvetica", 10, "bold"), padx=14, pady=6,
                       cursor="hand2", highlightthickness=0)
        btn.pack(side="left", padx=(0, 6))
        app._url_plat_btns[plat] = btn
    app._url_entry.bind("<KeyRelease>", lambda e: app._url_detect_platform())

    # ── Case title ────────────────────────────────────────────────────────
    title_row = tk.Frame(inner, bg=BG)
    title_row.pack(fill="x", padx=PAD, pady=(18, 4))
    tk.Label(title_row, text="CASE TITLE", bg=BG, fg=LIGHT_GRAY,
             font=("Helvetica", 10, "bold")).pack(side="left")
    app._url_ai_badge = tk.Label(title_row, text="  ✦ AI will auto-detect",
                                  bg=BG, fg="#5c5850", font=("Helvetica", 9))
    app._url_ai_badge.pack(side="left", padx=(8, 0))
    title_frame = tk.Frame(inner, bg="#1f1b18",
                           highlightthickness=1, highlightbackground="#332f2c")
    title_frame.pack(fill="x", padx=PAD)
    app._url_title_entry = tk.Entry(title_frame, bg="#1f1b18", fg=WHITE,
                                     insertbackground=WHITE, font=("Helvetica", 13),
                                     bd=0, relief="flat", highlightthickness=0)
    app._url_title_entry.pack(fill="x", padx=10, pady=10)

    # ── Buffer caption ────────────────────────────────────────────────────
    cap_row = tk.Frame(inner, bg=BG)
    cap_row.pack(fill="x", padx=PAD, pady=(18, 4))
    tk.Label(cap_row, text="BUFFER CAPTION", bg=BG, fg=LIGHT_GRAY,
             font=("Helvetica", 10, "bold")).pack(side="left")
    app._url_cap_badge = tk.Label(cap_row, text="  ✦ AI will generate",
                                   bg=BG, fg="#5c5850", font=("Helvetica", 9))
    app._url_cap_badge.pack(side="left", padx=(8, 0))
    cap_frame = tk.Frame(inner, bg="#1f1b18",
                         highlightthickness=1, highlightbackground="#332f2c")
    cap_frame.pack(fill="x", padx=PAD)
    app._url_caption_text = tk.Text(cap_frame, bg="#1f1b18", fg=WHITE,
                                     insertbackground=WHITE, font=("Helvetica", 12),
                                     bd=0, relief="flat", highlightthickness=0,
                                     wrap="word", height=7)
    app._url_caption_text.pack(fill="x", padx=10, pady=10)

    app._btn_use_my_caption = _make_lbtn(
        inner, "USE THIS CAPTION", app._start_url_use_my_caption,
        bg="#1f1b18", fg=LIGHT_GRAY, hover_bg="#2a2725", hover_fg=WHITE,
        font=("Helvetica", 10, "bold"), pady=9, padx=16
    )
    app._btn_use_my_caption.pack(padx=PAD, fill="x", pady=(8, 0))

    # ── Import & Schedule button ──────────────────────────────────────────
    btn_wrapper = tk.Frame(inner, bg=CRIMSON, padx=2, pady=2)
    btn_wrapper.pack(padx=PAD, pady=(20, 0), fill="x")
    app._btn_url_import = _make_lbtn(
        btn_wrapper, "IMPORT & SCHEDULE", app._start_url_import,
        bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
        font=("Helvetica", 14, "bold"), pady=16
    )
    app._btn_url_import.pack(fill="x")

    # ── Animation canvas ──────────────────────────────────────────────────
    app._url_anim_canvas = tk.Canvas(
        inner, bg="#141210", height=170,
        highlightthickness=1, highlightbackground="#2a2725"
    )
    app._url_anim_canvas.pack(padx=PAD, fill="x", pady=(18, 20))
    app._url_anim_canvas.bind("<Configure>", lambda e: app._url_anim_render())

    app._url_anim_state   = "idle"
    app._url_anim_phase   = 0.0
    app._url_anim_status  = ""
    app._url_anim_tick_id = None
    app.after(60, app._url_anim_render)

    # ── Retry & Schedule button (hidden until Archive.org poll exhausted) ──
    app._btn_retry_schedule = _make_lbtn(
        inner, "↻  RETRY & SCHEDULE", app._url_retry_schedule,
        bg="#123322", fg="#22c55e", hover_bg="#1a4a34", hover_fg=WHITE,
        font=("Helvetica", 12, "bold"), pady=12
    )
    # Packed/hidden dynamically — stays hidden until UploadPendingError

    # Check Ollama status after UI is built
    app.after(200, app._url_check_ollama_status)
