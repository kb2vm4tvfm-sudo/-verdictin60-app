"""Reusable VerdictIn60 UI components built on the theme tokens in theme.py.

These are small factory functions rather than tk widget subclasses so they stay
easy to drop into the existing Tkinter tab modules without restructuring how
those modules build their widgets.
"""
import tkinter as tk

from verdictin60_ui.theme import (
    CARD, CARD_ALT, BORDER, BORDER_LIGHT,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, TEXT_DIM,
    ACCENT, ACCENT_HOT, ACCENT_MUTED,
    SIDEBAR_BG, SURFACE,
    SUCCESS, SUCCESS_BG, WARNING, WARNING_BG, ERROR, ERROR_BG,
    FONT_FAMILY, SPACE_SM, SPACE_MD,
)
from verdictin60_ui.widgets import _make_lbtn

# Semantic status → (fg, bg) badge colors, shared by every "status pill" in the app.
STATUS_STYLES = {
    "success": (SUCCESS, SUCCESS_BG),
    "warning": (WARNING, WARNING_BG),
    "error":   (ERROR, ERROR_BG),
    "info":    (ACCENT, ACCENT_MUTED),
    "neutral": (TEXT_MUTED, CARD_ALT),
}


def make_card(parent, padx=18, pady=16, bg=CARD, border=BORDER, hover=True):
    """A rounded-feel bordered panel — the base surface for grouped content.
    Brightens its border on hover for a subtle "elevated" feel unless hover=False."""
    card = tk.Frame(parent, bg=bg, highlightthickness=1,
                     highlightbackground=border, highlightcolor=border)
    card._content = tk.Frame(card, bg=bg)
    card._content.pack(fill="both", expand=True, padx=padx, pady=pady)
    if hover:
        card.bind("<Enter>", lambda e: card.configure(highlightbackground=BORDER_LIGHT))
        card.bind("<Leave>", lambda e: card.configure(highlightbackground=border))
    return card


def card_body(card):
    """Return the padded inner frame of a make_card() panel."""
    return card._content


def make_badge(parent, text, status="neutral"):
    """A small status pill, e.g. Verified / Needs Review / Failed."""
    fg, bg = STATUS_STYLES.get(status, STATUS_STYLES["neutral"])
    return tk.Label(
        parent, text=f"  {text}  ", bg=bg, fg=fg,
        font=(FONT_FAMILY, 9, "bold"), padx=4, pady=3,
    )


def make_metric_card(parent, label, value, status="info"):
    """A compact metric tile: big value on top, muted label below."""
    fg, _bg = STATUS_STYLES.get(status, STATUS_STYLES["info"])
    card = make_card(parent, padx=16, pady=12)
    body = card_body(card)
    tk.Label(body, text=value, bg=CARD, fg=fg,
              font=(FONT_FAMILY, 20, "bold")).pack(anchor="w")
    tk.Label(body, text=label, bg=CARD, fg=TEXT_MUTED,
              font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(2, 0))
    return card


def make_empty_state(parent, text, bg=CARD):
    return tk.Label(
        parent, text=text, bg=bg,
        fg=TEXT_DIM, font=(FONT_FAMILY, 10), justify="center",
    )


def make_sidebar_button(parent, icon, text, command, width=None):
    """One entry in the left sidebar nav. Returns the row frame; call
    set_sidebar_active()/set_sidebar_inactive() to toggle its selected state."""
    row = tk.Frame(parent, bg=SIDEBAR_BG)
    if width:
        row.configure(width=width)
    accent_bar = tk.Frame(row, bg=SIDEBAR_BG, width=3)
    accent_bar.pack(side="left", fill="y")
    btn = _make_lbtn(
        row, f"{icon}   {text}", command,
        bg=SIDEBAR_BG, fg=TEXT_SECONDARY, hover_bg=CARD_ALT, hover_fg=TEXT,
        normal_fg=TEXT_SECONDARY, font=(FONT_FAMILY, 11), pady=10, padx=14,
        anchor="w",
    )
    btn.pack(fill="x", expand=True)
    row._accent_bar = accent_bar
    row._btn = btn
    return row


def set_sidebar_active(row):
    row._accent_bar.config(bg=ACCENT)
    row._btn.config(bg=ACCENT_MUTED, fg=ACCENT)
    row._btn._lbtn_normal_bg = ACCENT_MUTED
    row._btn._lbtn_normal_fg = ACCENT
    row._btn._lbtn_hover_bg = ACCENT_MUTED
    row._btn._lbtn_hover_fg = ACCENT


def set_sidebar_inactive(row):
    row._accent_bar.config(bg=SIDEBAR_BG)
    row._btn.config(bg=SIDEBAR_BG, fg=TEXT_SECONDARY)
    row._btn._lbtn_normal_bg = SIDEBAR_BG
    row._btn._lbtn_normal_fg = TEXT_SECONDARY
    row._btn._lbtn_hover_bg = CARD_ALT
    row._btn._lbtn_hover_fg = TEXT


def make_segmented_tabs(parent, options, on_select, initial=None):
    """A horizontal pill tab-bar, e.g. Settings: General / Appearance / AI / ...
    Returns (bar_frame, select_fn) — call select_fn(key) to switch programmatically."""
    bar = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
    inner = tk.Frame(bar, bg=SURFACE)
    inner.pack(padx=4, pady=4)

    buttons = {}

    def _select(key):
        for k, b in buttons.items():
            if k == key:
                b.config(bg=ACCENT_MUTED, fg=ACCENT)
            else:
                b.config(bg=SURFACE, fg=TEXT_SECONDARY)
        on_select(key)

    for key, label in options:
        b = _make_lbtn(
            inner, label, lambda k=key: _select(k),
            bg=SURFACE, fg=TEXT_SECONDARY, hover_bg=CARD_ALT, hover_fg=TEXT,
            font=(FONT_FAMILY, 10, "bold"), pady=8, padx=16,
        )
        b.pack(side="left")
        buttons[key] = b

    if initial is not None:
        _select(initial)

    return bar, _select


def make_top_bar(parent, title=""):
    """The slim top bar shared by every screen's header row.
    Returns (bar_frame, title_label) — update title_label's text to retitle it."""
    bar = tk.Frame(parent, bg=SURFACE, highlightthickness=0)
    tk.Frame(bar, bg=ACCENT, height=2).pack(fill="x", side="top")
    inner = tk.Frame(bar, bg=SURFACE)
    inner.pack(fill="x", padx=30, pady=SPACE_MD - 4)
    title_label = tk.Label(inner, text=title, bg=SURFACE, fg=TEXT,
                            font=(FONT_FAMILY, 13, "bold"))
    title_label.pack(side="left")
    return bar, title_label
