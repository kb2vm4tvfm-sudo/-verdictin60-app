"""Research Hub tab — search panel, Investigate button, and results view.

Static widget construction only, matching the split used by the other tab
modules: this file builds the shell and stateless presentational pieces
(source rows, case summary card); orchestration (threading, calling
verdictin60_core.research_hub, case library / clipboard / browser actions)
lives on the App instance in app.py, same as url_import_tab.py / app.py.
"""
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse

from verdictin60_ui.theme import (
    BG, CARD, CARD_ALT, BORDER, TEXT, TEXT_MUTED,
    ACCENT, ACCENT_HOT, INPUT_BG, DISABLED,
    FONT_FAMILY, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG,
)
from verdictin60_ui.components import (
    make_card, card_body, make_badge, make_confidence_badge,
    make_error_banner, make_empty_state,
)
from verdictin60_ui.widgets import _make_lbtn

PAD = 30

GROUP_SECTIONS = [
    ("official", "OFFICIAL SOURCES", "success"),
    ("reporting_accessible", "REPORTING (ACCESSIBLE)", "info"),
    ("reporting_archived", "REPORTING (ARCHIVED)", "warning"),
    ("blocked", "BLOCKED / INACCESSIBLE", "error"),
]


def _field_label(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_MUTED,
                     font=(FONT_FAMILY, 10, "bold"), anchor="w", justify="left",
                     wraplength=900)


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.") or url[:40]
    except Exception:
        return url[:40]


def build_research_tab(app, parent):
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

    # ── Search panel ─────────────────────────────────────────────────────
    _field_label(
        inner,
        "CLUES — person/victim/suspect name, case title, location, date, "
        "keywords, court case number, or any URL (Instagram/TikTok/YouTube/"
        "X/Facebook/Reddit/etc.) — one per line or paste freely",
    ).pack(anchor="w", padx=PAD, pady=(SPACE_LG - 6, SPACE_XS))

    clue_frame = tk.Frame(inner, bg=INPUT_BG, highlightthickness=1, highlightbackground=BORDER)
    clue_frame.pack(fill="x", padx=PAD)
    app._rh_clue_text = tk.Text(
        clue_frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
        font=(FONT_FAMILY, 12), bd=0, relief="flat", highlightthickness=0,
        wrap="word", height=8,
    )
    app._rh_clue_text.pack(fill="x", padx=10, pady=10)

    app._btn_rh_investigate = _make_lbtn(
        inner, "INVESTIGATE", app._rh_start_investigate,
        bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT,
        font=(FONT_FAMILY, 14, "bold"), pady=16,
    )
    app._btn_rh_investigate.pack(padx=PAD, pady=(SPACE_SM, 0), fill="x")

    # ── Status / error ───────────────────────────────────────────────────
    app._rh_status_lbl = tk.Label(
        inner, text="", bg=BG, fg=TEXT_MUTED, font=(FONT_FAMILY, 10),
        anchor="w", justify="left", wraplength=900,
    )
    app._rh_status_lbl.pack(anchor="w", padx=PAD, pady=(SPACE_SM, 0))

    app._rh_error_host = tk.Frame(inner, bg=BG)
    app._rh_error_host.pack(fill="x", padx=PAD)

    def _rh_show_error(message):
        for child in app._rh_error_host.winfo_children():
            child.destroy()
        make_error_banner(app._rh_error_host, message, title="Investigation error").pack(
            fill="x", pady=(SPACE_SM, 0))
    app._rh_show_error = _rh_show_error

    def _rh_hide_error():
        for child in app._rh_error_host.winfo_children():
            child.destroy()
    app._rh_hide_error = _rh_hide_error

    # ── Results (populated dynamically by app._rh_show_result) ─────────────
    app._rh_results_host = tk.Frame(inner, bg=BG)
    app._rh_results_host.pack(fill="both", expand=True, padx=PAD, pady=(SPACE_MD, SPACE_LG))
    render_empty_state(app._rh_results_host)


def render_empty_state(host):
    for child in host.winfo_children():
        child.destroy()
    make_empty_state(
        host,
        "Paste clues above and click Investigate to identify a case,\n"
        "gather official/reporting sources, and recover archived pages.",
        bg=BG,
    ).pack(pady=60)


def render_case_summary(parent, case: dict) -> tk.Frame:
    """A card with the identified case title, confidence, and AI reasoning."""
    card = make_card(parent, padx=18, pady=16, hover=False)
    body = card_body(card)

    header = tk.Frame(body, bg=CARD)
    header.pack(fill="x")
    tk.Label(header, text=case.get("case_title") or "Unidentified case",
              bg=CARD, fg=TEXT, font=(FONT_FAMILY, 15, "bold"),
              anchor="w", wraplength=700, justify="left").pack(side="left", fill="x", expand=True)

    badge = make_confidence_badge(header, case.get("confidence", "Very low"),
                                   case.get("confidence_reason", ""), bg=CARD)
    badge.pack(side="right", anchor="n")

    if case.get("aliases"):
        tk.Label(body, text="Aliases: " + ", ".join(case["aliases"]),
                  bg=CARD, fg=TEXT_MUTED, font=(FONT_FAMILY, 9),
                  anchor="w", wraplength=760, justify="left").pack(anchor="w", pady=(8, 0))

    if case.get("reasoning"):
        tk.Label(body, text=case["reasoning"], bg=CARD, fg=TEXT_MUTED,
                  font=(FONT_FAMILY, 10), anchor="w", wraplength=760,
                  justify="left").pack(anchor="w", pady=(8, 0))

    def _detail_row(label, value):
        if not value:
            return
        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", anchor="w", pady=(8, 0))
        tk.Label(row, text=label, bg=CARD, fg=TEXT_MUTED,
                  font=(FONT_FAMILY, 9, "bold"), width=14, anchor="w").pack(side="left")
        tk.Label(row, text=value, bg=CARD, fg=TEXT, font=(FONT_FAMILY, 10),
                  anchor="w", wraplength=620, justify="left").pack(side="left", fill="x", expand=True)

    _detail_row("Victims", ", ".join(case.get("victims", [])))
    _detail_row("Suspects", ", ".join(case.get("suspects", [])))
    _detail_row("Related", ", ".join(case.get("related_people", [])))
    _detail_row("Outcome", case.get("outcome", ""))
    if case.get("timeline"):
        _detail_row("Timeline", " → ".join(case["timeline"][:8]))

    return card


def render_stats_row(parent, stats: dict, elapsed_seconds) -> tk.Frame:
    row = tk.Frame(parent, bg=BG)
    checked = stats.get("sources_checked", 0)
    skipped = stats.get("skipped_slow_or_blocked", 0)
    stopped = stats.get("stopped_reason", "completed_full_search")
    text = (
        f"Investigated in {elapsed_seconds}s  •  {checked} source(s) checked  •  "
        f"{skipped} slow/blocked source(s) skipped  •  stopped: {stopped.replace('_', ' ')}"
    )
    tk.Label(row, text=text, bg=BG, fg=DISABLED, font=(FONT_FAMILY, 9),
              anchor="w", wraplength=900, justify="left").pack(anchor="w")
    return row


def _source_row(parent, src: dict, bg) -> tk.Frame:
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", anchor="w", pady=4)

    top = tk.Frame(row, bg=bg)
    top.pack(fill="x", anchor="w")

    if src.get("archived_accessible"):
        status_text, status_kind = "Archived", "warning"
    elif src.get("blocked"):
        status_text, status_kind = "Blocked", "error"
    else:
        status_text, status_kind = "Accessible", "success"
    make_badge(top, status_text, status=status_kind).pack(side="left")
    make_badge(top, src.get("kind", "Reference"), status="neutral").pack(side="left", padx=(4, 0))
    if src.get("is_pdf"):
        make_badge(top, "PDF", status="neutral").pack(side="left", padx=(4, 0))

    tk.Label(
        top, text=src.get("title") or _domain_of(src.get("url", "")),
        bg=bg, fg=TEXT, font=(FONT_FAMILY, 10, "bold"),
        anchor="w", wraplength=560, justify="left",
    ).pack(side="left", padx=(8, 0), fill="x", expand=True)

    tk.Label(row, text=src.get("url", ""), bg=bg, fg=TEXT_MUTED,
              font=(FONT_FAMILY, 8), anchor="w", wraplength=760,
              justify="left").pack(anchor="w", pady=(2, 0))

    archive = src.get("archive") or {}
    if archive.get("archive_url"):
        tk.Label(
            row, text=f"Archive provider: {archive.get('provider', 'Wayback Machine')}  "
                      f"•  Date: {archive.get('archived_at', '—')}  •  {archive['archive_url']}",
            bg=bg, fg=TEXT_MUTED, font=(FONT_FAMILY, 8), anchor="w",
            wraplength=760, justify="left",
        ).pack(anchor="w", pady=(2, 0))
    elif archive.get("manual_links"):
        links = "  |  ".join(f"{m['provider']}" for m in archive["manual_links"])
        tk.Label(row, text=f"Manual archive lookup available: {links}",
                  bg=bg, fg=TEXT_MUTED, font=(FONT_FAMILY, 8), anchor="w",
                  wraplength=760, justify="left").pack(anchor="w", pady=(2, 0))

    notes = src.get("inaccessible_reason") or (
        "Verified: case name confirmed on the page." if not src.get("blocked") else ""
    )
    if notes:
        tk.Label(row, text=f"Notes: {notes}", bg=bg, fg=DISABLED, font=(FONT_FAMILY, 8),
                  anchor="w", wraplength=760, justify="left").pack(anchor="w", pady=(2, 0))

    return row


def render_source_group(parent, title: str, sources: list, status: str) -> tk.Frame:
    card = make_card(parent, padx=16, pady=12, hover=False)
    body = card_body(card)
    header = tk.Frame(body, bg=CARD)
    header.pack(fill="x")
    tk.Label(header, text=title, bg=CARD, fg=TEXT, font=(FONT_FAMILY, 11, "bold"),
              anchor="w").pack(side="left")
    make_badge(header, str(len(sources)), status=status).pack(side="left", padx=(8, 0))

    if not sources:
        tk.Label(body, text="None found.", bg=CARD, fg=DISABLED,
                  font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(8, 0))
        return card

    for i, src in enumerate(sources):
        row_bg = CARD if i % 2 == 0 else CARD_ALT
        _source_row(body, src, row_bg)
    return card


def render_action_bar(parent, actions: list) -> tk.Frame:
    """actions: list of (label, command) tuples."""
    bar = tk.Frame(parent, bg=BG)
    bar.pack(fill="x", pady=(SPACE_MD, 0))
    for label, command in actions:
        btn = _make_lbtn(
            bar, label, command, bg=CARD_ALT, fg=TEXT_MUTED,
            hover_bg=BORDER, hover_fg=TEXT, font=(FONT_FAMILY, 9, "bold"),
            pady=9, padx=12,
        )
        btn.pack(side="left", padx=(0, 6), pady=(6, 0))
    return bar
