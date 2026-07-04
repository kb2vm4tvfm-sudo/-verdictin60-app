import tkinter as tk
from tkinter import ttk

from verdictin60_ui.theme import (
    BG, INPUT_BG, BORDER, TEXT, TEXT_MUTED, ACCENT, ACCENT_HOT,
    FONT_FAMILY, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG,
)
from verdictin60_ui.components import make_empty_state
from verdictin60_ui.widgets import _make_lbtn

PAD = 30


def _field_label(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_MUTED, font=(FONT_FAMILY, 10, "bold"))


def build_research_tab(app, parent):
    """All-in-one investigation workspace: paste any combination of clues or
    links, then Investigate to identify the case, gather sources, and recover
    archived pages. See app.py's "Research Hub tab" section for the handlers
    (`_research_*`) that drive this UI."""
    scroll_outer = tk.Frame(parent, bg=BG)
    scroll_outer.pack(fill="both", expand=True)
    canvas_scroll = tk.Canvas(scroll_outer, bg=BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(scroll_outer, orient="vertical", command=canvas_scroll.yview)
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

    tk.Label(inner, text="RESEARCH HUB", bg=BG, fg=TEXT,
             font=(FONT_FAMILY, 16, "bold")).pack(anchor="w", padx=PAD, pady=(SPACE_LG - 6, 4))
    tk.Label(
        inner,
        text=("Paste any combination of names, locations, dates, keywords, or links "
              "(Instagram / TikTok / YouTube / X / Facebook / Reddit / any URL) — one per "
              "line or as free text. Investigate identifies the most likely case, gathers "
              "official/legal/reporting sources, and recovers archived pages automatically."),
        bg=BG, fg=TEXT_MUTED, font=(FONT_FAMILY, 10), wraplength=760, justify="left",
    ).pack(anchor="w", padx=PAD, pady=(0, SPACE_MD))

    # ── Search panel ──────────────────────────────────────────────────────
    _field_label(inner, "CASE CLUES").pack(anchor="w", padx=PAD, pady=(0, SPACE_XS))
    input_frame = tk.Frame(inner, bg=INPUT_BG, highlightthickness=1, highlightbackground=BORDER)
    input_frame.pack(fill="x", padx=PAD)
    app._research_input = tk.Text(
        input_frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
        font=(FONT_FAMILY, 11), bd=0, relief="flat", highlightthickness=0,
        wrap="word", height=6,
    )
    app._research_input.pack(fill="x", padx=10, pady=10)

    app._btn_investigate = _make_lbtn(
        inner, "INVESTIGATE", app._research_start_investigation,
        bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT,
        font=(FONT_FAMILY, 14, "bold"), pady=14,
    )
    app._btn_investigate.pack(fill="x", padx=PAD, pady=(SPACE_SM, 0))

    # ── Status / progress ─────────────────────────────────────────────────
    app._research_status_host = tk.Frame(inner, bg=BG)
    app._research_status_host.pack(fill="x", padx=PAD, pady=(SPACE_SM, 0))

    # ── Results ───────────────────────────────────────────────────────────
    app._research_results_host = tk.Frame(inner, bg=BG)
    app._research_results_host.pack(fill="both", expand=True, padx=PAD, pady=(SPACE_LG, SPACE_LG))
    make_empty_state(
        app._research_results_host,
        "Paste clues above and click Investigate to build a case file.",
        bg=BG,
    ).pack(anchor="w", pady=30)
