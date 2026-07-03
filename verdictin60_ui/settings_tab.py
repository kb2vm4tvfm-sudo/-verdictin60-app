"""Settings dialog, moved from app.py (Phase 8 refactor, no behavior change)."""
import tkinter as tk
from tkinter import ttk

from verdictin60_core.settings import load_settings, save_settings
from verdictin60_core.ai import AI_SPEED_MODES
from verdictin60_ui import BG, CRIMSON, CRIMSON_HOT, WHITE, _make_lbtn


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, True)

        s = load_settings()

        # Top accent bar
        tk.Frame(self, bg=CRIMSON, height=3).pack(fill="x")

        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=30, pady=(24, 0))
        tk.Label(hdr, text="SETTINGS", font=("Helvetica", 14, "bold"),
                 fg=WHITE, bg=BG, anchor="w").pack(side="left")

        fields_frame = tk.Frame(self, bg=BG)
        fields_frame.pack(padx=30, fill="x", pady=(8, 0))

        self._vars = {}

        # ── Buffer section ────────────────────────────────────────────────────
        tk.Frame(fields_frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(12, 8))
        tk.Label(fields_frame, text="BUFFER", font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        buffer_rows = [
            ("buffer_key",        "Buffer API Key",              s.get("buffer_key", ""),        True),
            ("buffer_channel_id", "Buffer Instagram Channel ID", s.get("buffer_channel_id", ""), False),
            ("post_time",         "Daily Post Time (HH:MM)",     s.get("post_time", "18:00"),    False),
        ]
        for key, label, value, masked in buffer_rows:
            self._make_field(fields_frame, key, label, value, masked)

        # ── Internet Archive section ──────────────────────────────────────────
        tk.Frame(fields_frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(20, 8))
        tk.Label(fields_frame, text="INTERNET ARCHIVE  —  VIDEO HOSTING", font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        ia_rows = [
            ("ia_access_key", "IA Access Key",  s.get("ia_access_key", ""),  False),
            ("ia_secret_key", "IA Secret Key",  s.get("ia_secret_key", ""),  True),
        ]
        for key, label, value, masked in ia_rows:
            self._make_field(fields_frame, key, label, value, masked)

        # ── AI section ────────────────────────────────────────────────────────
        tk.Frame(fields_frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(20, 8))
        tk.Label(fields_frame, text="AI  —  OLLAMA SETTINGS", font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        tk.Label(fields_frame, text="AI SPEED MODE", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        ai_speed_options = [
            "Fast",
            "Balanced",
            "Best Accuracy",
        ]
        current_speed = s.get("ai_speed_mode", "")
        if current_speed not in AI_SPEED_MODES:
            current_ai = s.get("ai_model", "qwen3:14b")
            current_speed = "Best Accuracy" if current_ai == "qwen3:32b" else "Balanced"
        self._ai_speed_var = tk.StringVar(value=current_speed or "Balanced")
        ai_dropdown = ttk.Combobox(
            fields_frame, textvariable=self._ai_speed_var,
            values=ai_speed_options, state="readonly",
            font=("Helvetica", 11)
        )
        ai_dropdown.pack(fill="x", ipady=4)

        tk.Label(fields_frame, text="PREFERRED BROWSER FOR COOKIES", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        browser_options = ["chrome", "safari", "firefox"]
        self._browser_var = tk.StringVar(value=s.get("preferred_browser", "chrome"))
        browser_dropdown = ttk.Combobox(
            fields_frame, textvariable=self._browser_var,
            values=browser_options, state="readonly",
            font=("Helvetica", 11)
        )
        browser_dropdown.pack(fill="x", ipady=4)

        # ── Save button ───────────────────────────────────────────────────────
        tk.Frame(self, bg="#2a2a2a", height=1).pack(fill="x", padx=30, pady=(20, 0))
        btn = _make_lbtn(
            self, "SAVE SETTINGS", self._save,
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 11, "bold"), pady=12, padx=20
        )
        btn.pack(padx=30, fill="x", pady=(12, 24))

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        dw, dh = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"{max(dw, 420)}x{dh}+{px+(pw-dw)//2}+{py+(ph-dh)//2}")

    def _make_field(self, parent, key, label, value, masked):
        tk.Label(parent, text=label.upper(), font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        e = tk.Entry(parent, show="*" if masked else "",
                     font=("Helvetica", 11), fg=WHITE, bg="#1a1a1a",
                     insertbackground=WHITE, relief="flat",
                     highlightthickness=1, highlightbackground="#2a2a2a",
                     highlightcolor=CRIMSON)
        e.insert(0, value)
        e.pack(fill="x", ipady=8)
        var = tk.StringVar(value=value)
        e.config(textvariable=var)
        self._vars[key] = var

    def _save(self):
        current = load_settings()
        current.update({k: v.get().strip() for k, v in self._vars.items()})
        speed_mode = self._ai_speed_var.get().strip()
        if speed_mode not in AI_SPEED_MODES:
            speed_mode = "Balanced"
        current["ai_speed_mode"] = speed_mode
        current["ai_model"] = AI_SPEED_MODES[speed_mode]["caption"]
        current["preferred_browser"] = self._browser_var.get().strip()
        save_settings(current)
        self.destroy()
