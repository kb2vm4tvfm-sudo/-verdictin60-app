import tkinter as tk

from verdictin60_ui.widgets import BG, CRIMSON, CRIMSON_HOT, WHITE, LIGHT_GRAY, _make_lbtn


def build_recovery_tab(app, parent):
    PAD = 36
    inner = tk.Frame(parent, bg=BG)
    inner.pack(fill="both", expand=True, padx=PAD, pady=(24, 0))

    tk.Label(inner, text="RECOVERY ASSISTANT",
             bg=BG, fg=WHITE, font=("Helvetica", 16, "bold")).pack(anchor="w")
    tk.Label(
        inner,
        text="Local rule-based diagnostics. Repairs always require approval.",
        bg=BG, fg=LIGHT_GRAY, font=("Helvetica", 10),
        wraplength=640, justify="left"
    ).pack(anchor="w", pady=(4, 14))

    btn_row = tk.Frame(inner, bg=BG)
    btn_row.pack(fill="x", pady=(0, 12))
    _make_lbtn(
        btn_row, "SCAN ENTIRE APPLICATION", app._recovery_run_scan,
        bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
        font=("Helvetica", 11, "bold"), pady=12, padx=18
    ).pack(side="left")

    app._recovery_overall = tk.Label(
        inner, text="Status: not scanned yet",
        bg=BG, fg=LIGHT_GRAY, font=("Helvetica", 10, "bold")
    )
    app._recovery_overall.pack(anchor="w", pady=(0, 10))

    app._recovery_results = tk.Frame(inner, bg=BG)
    app._recovery_results.pack(fill="both", expand=True)
