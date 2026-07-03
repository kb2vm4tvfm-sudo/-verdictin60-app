import tkinter as tk

BG          = "#000000"
CRIMSON     = "#940906"
CRIMSON_HOT = "#6b0604"
ERROR_RED   = "#ff4444"
WHITE       = "#FFFFFF"
OFF_WHITE   = "#e8e8e8"
MUTED       = "#555555"
LIGHT_GRAY  = "#888888"
DARK_CARD   = "#0e0e0e"
ROW_BG      = "#0d0d0d"
ROW_ALT     = "#111111"


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


def _lbtn_disable(lbl, bg, fg="#888888"):
    lbl._lbtn_disabled = True
    lbl.config(bg=bg, fg=fg)
