import tkinter as tk

from verdictin60_ui.theme import (
    BG, CARD, CARD_ALT, TEXT, TEXT_OFF, TEXT_MUTED, DISABLED,
    ACCENT, ACCENT_HOT, ERROR,
)

# Back-compat aliases used throughout app.py / verdictin60_ui / case_library.py.
# The names are historic (this app used to have a crimson/red theme) but now
# resolve to the VerdictIn60 dark-navy/cyan palette defined in theme.py.
CRIMSON     = ACCENT
CRIMSON_HOT = ACCENT_HOT
ERROR_RED   = ERROR
WHITE       = TEXT
OFF_WHITE   = TEXT_OFF
MUTED       = DISABLED
LIGHT_GRAY  = TEXT_MUTED
DARK_CARD   = CARD
ROW_BG      = CARD
ROW_ALT     = CARD_ALT


def _bind_hover(widget, normal_bg, hover_bg, normal_fg=None, hover_fg=None):
    def on_enter(_):
        if getattr(widget, "_lbtn_disabled", False):
            return
        widget.config(bg=hover_bg)
        if hover_fg:
            widget.config(fg=hover_fg)
    def on_leave(_):
        if getattr(widget, "_lbtn_disabled", False):
            return
        widget.config(bg=normal_bg)
        if normal_fg:
            widget.config(fg=normal_fg)
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


def _make_lbtn(parent, text, command, bg, fg=WHITE, font=("Helvetica", 12, "bold"),
               hover_bg=None, hover_fg=None, pady=14, padx=20, anchor="center",
               normal_fg=None):
    """tk.Label styled as a button — respects bg on macOS unlike tk.Button."""
    if hover_bg is None:
        hover_bg = bg
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                   cursor="hand2", pady=pady, padx=padx, anchor=anchor,
                   highlightthickness=0)
    lbl._lbtn_disabled = False
    lbl._lbtn_normal_bg = bg
    lbl._lbtn_hover_bg  = hover_bg
    lbl._lbtn_normal_fg = normal_fg or fg
    lbl._lbtn_hover_fg  = hover_fg or fg
    lbl._lbtn_command   = command

    def _click(e):
        if not lbl._lbtn_disabled:
            command()
    def _enter(e):
        if not lbl._lbtn_disabled:
            lbl.config(bg=hover_bg, fg=lbl._lbtn_hover_fg)
    def _leave(e):
        if not lbl._lbtn_disabled:
            lbl.config(bg=bg, fg=lbl._lbtn_normal_fg)

    lbl.bind("<Button-1>", _click)
    lbl.bind("<Enter>", _enter)
    lbl.bind("<Leave>", _leave)
    return lbl


def _lbtn_enable(lbl, bg, fg=WHITE, hover_bg=None):
    lbl._lbtn_disabled = False
    lbl._lbtn_normal_bg = bg
    lbl._lbtn_hover_bg = hover_bg or bg
    lbl._lbtn_normal_fg = fg
    lbl.config(bg=bg, fg=fg)


def _lbtn_disable(lbl, bg, fg=TEXT_MUTED):
    lbl._lbtn_disabled = True
    lbl.config(bg=bg, fg=fg)
