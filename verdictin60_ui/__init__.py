"""Shared Tkinter theme constants and widget helpers, moved from app.py (Phase 8 refactor, no behavior change).

These are the low-level building blocks (colors, hover-styled label buttons,
and canvas drawing helpers) used across all tab modules in this package as
well as by ``app.py`` itself.
"""
import math

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


def _draw_watermarks(canvas, w, h):
    c = "#1a1a1a"
    for x1, y1, x2, y2 in [(28, 60, 68, 100), (20, 50, 30, 60), (66, 98, 76, 108)]:
        canvas.create_rectangle(x1, y1, x2, y2, fill=c, outline="")
    canvas.create_rectangle(20, 95, 80, 102, fill=c, outline="")
    cx, cy, r = w - 55, h - 65, 22
    canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=c, width=5)
    canvas.create_line(cx+int(r*.7), cy+int(r*.7), cx+int(r*1.7), cy+int(r*1.7), fill=c, width=5)
    bx, by = w - 55, 75
    for i in range(5):
        rr = 10 + i * 8
        canvas.create_arc(bx-rr, by-rr//2, bx+rr, by+rr//2,
                          start=200, extent=140, style="arc", outline=c, width=2)
    pts, bx2, by2, br = [], 55, h - 65, 28
    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        pts += [bx2 + br * math.cos(rad), by2 + br * math.sin(rad)]
    canvas.create_polygon(pts, outline=c, fill="", width=2)
    canvas.create_oval(bx2-15, by2-15, bx2+15, by2+15, outline=c, width=2)


def _draw_grain(canvas, w, h):
    for gy in range(0, h, 18):
        for gx in range(0, w, 18):
            shade = "#0d0d0d" if (gx // 18 + gy // 18) % 2 == 0 else "#0a0a0a"
            canvas.create_rectangle(gx, gy, gx+1, gy+1, fill=shade, outline="")


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


# ── Shared canvas animation drawing ──────────────────────────────────────────
def _draw_anim(c, state, phase, status_txt, idle_hint=""):
    import math as _math
    cw = c.winfo_width()
    ch = c.winfo_height()
    if cw < 10:
        return
    c.delete("all")

    cx = cw // 2

    FOLDER_MID   = "#9B7A2E"
    FOLDER_DARK  = "#5C4010"
    FOLDER_LIGHT = "#C4A04A"
    PAGE_COL     = "#E8E4D8"
    GAVEL_HEAD   = "#DDDDDD"
    GAVEL_SHADE  = "#AAAAAA"
    HANDLE_COL   = "#8B6030"

    fw, fh = 224, 78
    fy_base = 55
    fx1, fy1 = cx - fw // 2, fy_base
    fx2, fy2 = cx + fw // 2, fy_base + fh
    tw, th = 68, 17
    tx1, ty1 = fx1 + 14, fy1 - th
    tx2, ty2 = tx1 + tw, fy1

    open_amt = 0.0
    if state == "processing":
        open_amt = max(0.0, _math.sin(phase * _math.pi * 2)) ** 0.6
    elif state == "scheduling":
        open_amt = 0.75 + 0.05 * _math.sin(phase * _math.pi * 4)
    elif state == "success":
        open_amt = max(0.0, 0.6 - phase * 1.7) if phase < 0.35 else 0.0

    if open_amt > 0.04:
        rise = int(open_amt * 44)
        for i, (x_off, col) in enumerate([(-28, "#D4D0C4"), (0, PAGE_COL), (28, "#DEDAD0")]):
            c.create_rectangle(
                cx + x_off - 20, fy1 - rise + 18 + i * 2,
                cx + x_off + 20, fy1 + 14,
                fill=col, outline="#B0AC9C", width=1
            )
            for li in range(3):
                ly = fy1 - rise + 26 + i * 2 + li * 6
                if ly < fy1 + 10:
                    c.create_line(cx + x_off - 13, ly, cx + x_off + 13, ly,
                                  fill="#888880", width=1)

    c.create_rectangle(fx1, fy1, fx2, fy2,
                       fill=FOLDER_MID, outline=FOLDER_DARK, width=2)
    c.create_rectangle(fx1 + 2, fy1 + 2, fx2 - 2, fy1 + 10,
                       fill=FOLDER_LIGHT, outline="")
    c.create_polygon(
        tx1 + 6, ty1, tx2, ty1,
        tx2, ty2, tx1, ty2,
        fill=FOLDER_LIGHT, outline=FOLDER_DARK, width=2
    )

    alpha_text = max(0.0, 1.0 - open_amt * 2.5)
    if alpha_text > 0.3:
        gray_val = int(0xFF * alpha_text)
        txt_col  = f"#{gray_val:02x}{gray_val:02x}{gray_val:02x}"
        c.create_text(cx, fy1 + fh // 2 + 2,
                      text="CASE FILE", font=("Helvetica", 10, "bold"), fill=txt_col)

    if state in ("processing", "scheduling"):
        pulse = (_math.sin(phase * _math.pi * 6) + 1) / 2
        r = 4 + int(pulse * 2)
        dx, dy = fx2 - 14, fy1 + 10
        c.create_oval(dx - r, dy - r, dx + r, dy + r, fill=CRIMSON, outline="")

    if state == "success":
        impact_phase = min(1.0, phase / 0.35)
        gavel_y = int(-60 + impact_phase * (fy1 - 22 + 60))
        if 0.34 < phase < 0.60:
            c.configure(highlightbackground=CRIMSON, highlightthickness=2)
        else:
            c.configure(highlightbackground="#2a2a2a", highlightthickness=1)
        gh_w, gh_h = 80, 24
        ghx1, ghy1 = cx - gh_w // 2, gavel_y
        ghx2, ghy2 = cx + gh_w // 2, gavel_y + gh_h
        c.create_rectangle(ghx1, ghy1, ghx2, ghy2,
                           fill=GAVEL_HEAD, outline=GAVEL_SHADE, width=2)
        c.create_rectangle(ghx1 + 3, ghy1 + 3, ghx2 - 3, ghy1 + 8,
                           fill="#F0F0F0", outline="")
        hx1, hy1 = cx + 28, gavel_y + 16
        hx2, hy2 = cx + 28 + 36, gavel_y + 16 + 55
        c.create_polygon(
            hx1, hy1, hx1 + 10, hy1,
            hx2 + 10, hy2, hx2, hy2,
            fill=HANDLE_COL, outline=FOLDER_DARK, width=1
        )
        if phase > 0.45:
            alpha = min(1.0, (phase - 0.45) / 0.25)
            gray  = int(0xFF * alpha)
            scheduled_col = f"#{gray:02x}{gray:02x}{gray:02x}"
            c.create_text(cx, fy2 + 28,
                          text="✓  SCHEDULED",
                          font=("Helvetica", 15, "bold"),
                          fill=scheduled_col)

    if status_txt and state not in ("success",):
        clean = status_txt.lstrip("⏳📅🔴✅✓ ")
        c.create_text(cx, fy2 + 20, text=clean,
                      font=("Courier", 9), fill=LIGHT_GRAY,
                      width=cw - 40)
    elif state == "idle" and not status_txt:
        c.create_text(cx, fy2 + 20, text=idle_hint,
                      font=("Courier", 9), fill="#444444")
    elif state == "error" and status_txt:
        clean = status_txt.lstrip("✗✓ ")
        c.create_text(cx, fy2 + 20, text=clean,
                      font=("Courier", 9), fill=ERROR_RED,
                      width=cw - 40)
