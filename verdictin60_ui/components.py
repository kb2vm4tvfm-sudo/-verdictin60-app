"""Reusable VerdictIn60 UI components built on the theme tokens in theme.py.

These are small factory functions rather than tk widget subclasses so they stay
easy to drop into the existing Tkinter tab modules without restructuring how
those modules build their widgets.
"""
import tkinter as tk

from verdictin60_ui.theme import (
    BG, CARD, CARD_ALT, BORDER, BORDER_LIGHT,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, TEXT_DIM,
    ACCENT, ACCENT_HOT, ACCENT_MUTED,
    SIDEBAR_BG, SURFACE,
    SUCCESS, SUCCESS_BG, WARNING, WARNING_BG, ERROR, ERROR_BG,
    FONT_FAMILY, SPACE_SM, SPACE_MD, SPACE_LG,
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

# Verification-confidence label → STATUS_STYLES key, covering both the
# High/Medium/Low/Very low vocabulary from verification_confidence() in
# verdictin60_core/research.py and the Verified/Needs Review/Not Verified
# vocabulary used elsewhere in the UI.
CONFIDENCE_STATUS = {
    "high": "success",
    "verified": "success",
    "medium": "info",
    "needs review": "warning",
    "low": "warning",
    "very low": "error",
    "not verified": "error",
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


def make_loading_state(parent, message="Loading…", bg=CARD):
    """A lightweight pulsing-dot + message row for in-progress states, meant to
    replace the various bespoke canvas animations across the tab modules.
    Call stop_loading_state(frame) before destroying it to cancel the pulse."""
    frame = tk.Frame(parent, bg=bg)
    dot = tk.Label(frame, text="●", bg=bg, fg=ACCENT, font=(FONT_FAMILY, 12, "bold"))
    dot.pack(side="left", padx=(0, SPACE_SM))
    tk.Label(frame, text=message, bg=bg, fg=TEXT_MUTED,
             font=(FONT_FAMILY, 10)).pack(side="left")

    frame._loading_job = None
    pulse_colors = (ACCENT, TEXT_DIM)

    def _tick(i=0):
        if not dot.winfo_exists():
            return
        dot.config(fg=pulse_colors[i % 2])
        frame._loading_job = frame.after(500, _tick, i + 1)

    _tick()
    return frame


def stop_loading_state(frame):
    """Cancel a make_loading_state() frame's pulse animation. Safe to call
    multiple times; call this before destroying the frame to avoid a stray
    .after() callback firing on a dead widget."""
    job = getattr(frame, "_loading_job", None)
    if job:
        frame.after_cancel(job)
        frame._loading_job = None


def make_error_banner(parent, message, title="Something went wrong", on_retry=None,
                       bg=ERROR_BG, border=ERROR):
    """A standard error surface — heading + message, with an optional retry
    action — replacing the ad hoc warning frames hand-built in app.py's dialogs."""
    banner = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=border)
    inner = tk.Frame(banner, bg=bg)
    inner.pack(fill="x", padx=SPACE_SM + 4, pady=SPACE_SM)
    tk.Label(inner, text=f"⚠  {title}", bg=bg, fg=ERROR,
             font=(FONT_FAMILY, 9, "bold")).pack(anchor="w")
    tk.Label(inner, text=message, bg=bg, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9),
             wraplength=460, justify="left").pack(anchor="w", pady=(2, 0))
    if on_retry:
        retry_btn = _make_lbtn(
            inner, "RETRY", on_retry, bg=bg, fg=ERROR,
            hover_bg=CARD_ALT, hover_fg=TEXT,
            font=(FONT_FAMILY, 9, "bold"), pady=4, padx=0, anchor="w",
        )
        retry_btn.pack(anchor="w", pady=(6, 0))
    return banner


def make_source_list(parent, sources, heading=None, max_items=8,
                      bg=CARD_ALT, border=BORDER):
    """A bordered panel of verification source rows (badge + title + URL),
    matching the "SOURCES FOUND" panel currently hand-built inline in the
    review dialog (app.py's _show_review_dialog)."""
    frame = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=border)
    inner = tk.Frame(frame, bg=bg)
    inner.pack(fill="both", expand=True, padx=SPACE_SM + 4, pady=SPACE_SM)

    if heading:
        tk.Label(inner, text=heading, bg=bg, fg=TEXT_SECONDARY,
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 4))

    if not sources:
        tk.Label(inner, text="No independent sources found.", bg=bg,
                 fg=TEXT_DIM, font=(FONT_FAMILY, 9)).pack(anchor="w")
        return frame

    for src in sources[:max_items]:
        row = tk.Frame(inner, bg=bg)
        row.pack(fill="x", anchor="w", pady=1)
        kind = "blocked" if src.get("blocked") else src.get("kind", "Source")
        status = "error" if src.get("blocked") else "neutral"
        make_badge(row, kind, status=status).pack(side="left", padx=(0, SPACE_SM))
        tk.Label(
            row, text=f"{src.get('title', 'Source')} — {src.get('url', '')}",
            bg=bg, fg=TEXT_MUTED, font=(FONT_FAMILY, 8),
            wraplength=460, justify="left", anchor="w",
        ).pack(side="left", fill="x", expand=True)
    return frame


def make_confidence_badge(parent, label, reason=None, bg=CARD):
    """A verification-confidence pill built on STATUS_STYLES via CONFIDENCE_STATUS
    (High/Medium/Low/Very low, or Verified/Needs Review/Not Verified), with an
    optional muted reason line underneath — e.g. the confidence_reason string
    returned alongside confidence_label by verification_confidence()."""
    status = CONFIDENCE_STATUS.get(str(label).strip().lower(), "neutral")
    if not reason:
        return make_badge(parent, label, status=status)
    wrap = tk.Frame(parent, bg=bg)
    make_badge(wrap, label, status=status).pack(anchor="w")
    tk.Label(wrap, text=reason, bg=bg, fg=TEXT_MUTED, font=(FONT_FAMILY, 9),
             wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))
    return wrap


def make_toplevel_shell(parent, title, width=520, height=400):
    """A standard Toplevel dialog shell: centered on screen, with a titled
    header row (and close button) and a content body frame, replacing the
    ~15 lines of boilerplate repeated by every tk.Toplevel dialog in app.py.
    Returns (win, body) — pack dialog-specific content into `body`."""
    win = tk.Toplevel(parent, bg=BG)
    win.title(title)
    win.geometry(f"{width}x{height}")
    win.resizable(False, False)
    win.grab_set()

    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{width}x{height}+{(sw - width) // 2}+{(sh - height) // 2}")

    header = tk.Frame(win, bg=BG)
    header.pack(fill="x", padx=SPACE_LG, pady=(SPACE_MD, SPACE_SM))
    tk.Label(header, text=title, bg=BG, fg=TEXT,
             font=(FONT_FAMILY, 13, "bold")).pack(side="left")
    close_btn = _make_lbtn(
        header, "✕", win.destroy, bg=BG, fg=TEXT_MUTED,
        hover_bg=BG, hover_fg=TEXT, font=(FONT_FAMILY, 12, "bold"),
        pady=0, padx=6,
    )
    close_btn.pack(side="right")

    tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=SPACE_LG)

    body = tk.Frame(win, bg=BG)
    body.pack(fill="both", expand=True, padx=SPACE_LG, pady=SPACE_MD)

    return win, body
