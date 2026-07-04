import tkinter as tk
from tkinter import ttk

from verdictin60_core.settings import load_settings, save_settings
from verdictin60_core.ai import AI_SPEED_MODES
from verdictin60_ui.widgets import BG, CRIMSON, CRIMSON_HOT, WHITE, LIGHT_GRAY, _make_lbtn
from verdictin60_ui.theme import CARD, BORDER, TEXT_SECONDARY, TEXT_MUTED, INPUT_BG
from verdictin60_ui.components import make_segmented_tabs, make_card, card_body

SETTINGS_TABS = [
    ("general", "General"),
    ("appearance", "Appearance"),
    ("ai", "AI"),
    ("models", "Models"),
    ("verification", "Verification"),
    ("exports", "Exports"),
    ("advanced", "Advanced"),
]


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, True)

        s = load_settings()
        self._vars = {}

        # Top accent bar
        tk.Frame(self, bg=CRIMSON, height=3).pack(fill="x")

        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=30, pady=(24, 0))
        tk.Label(hdr, text="SETTINGS", font=("Helvetica", 16, "bold"),
                 fg=WHITE, bg=BG, anchor="w").pack(side="left")
        tk.Label(self, text="Configure your VerdictIn60 workspace",
                 font=("Helvetica", 9), fg=LIGHT_GRAY, bg=BG, anchor="w"
                 ).pack(fill="x", padx=30, pady=(2, 0))

        # ── Segmented tabs ────────────────────────────────────────────────────
        tabs_wrap = tk.Frame(self, bg=BG)
        tabs_wrap.pack(fill="x", padx=30, pady=(16, 0))

        panels_host = tk.Frame(self, bg=BG)
        panels_host.pack(fill="both", expand=True, padx=30, pady=(14, 0))

        self._panels = {
            "general":      self._build_general(panels_host, s),
            "appearance":   self._build_appearance(panels_host),
            "ai":           self._build_ai(panels_host, s),
            "models":       self._build_models(panels_host),
            "verification": self._build_verification(panels_host),
            "exports":      self._build_exports(panels_host, s),
            "advanced":     self._build_advanced(panels_host, s),
        }

        def _show_panel(key):
            for p in self._panels.values():
                p.pack_forget()
            self._panels[key].pack(fill="both", expand=True)

        bar, _select = make_segmented_tabs(tabs_wrap, SETTINGS_TABS, _show_panel, initial="general")
        bar.pack(anchor="w")

        # ── Save button ───────────────────────────────────────────────────────
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(16, 0))
        btn = _make_lbtn(
            self, "SAVE SETTINGS", self._save,
            bg=CRIMSON, fg=WHITE, hover_bg=CRIMSON_HOT,
            font=("Helvetica", 11, "bold"), pady=12, padx=20
        )
        btn.pack(padx=30, fill="x", pady=(12, 24))

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        dw, dh = 620, 600
        self.geometry(f"{dw}x{dh}+{px+(pw-dw)//2}+{py+(ph-dh)//2}")

    # ── Panel builders ────────────────────────────────────────────────────────

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 6))

    def _build_general(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "BUFFER")
        rows = [
            ("buffer_key",        "Buffer API Key",              s.get("buffer_key", ""),        True),
            ("buffer_channel_id", "Buffer Instagram Channel ID", s.get("buffer_channel_id", ""), False),
            ("post_time",         "Daily Post Time (HH:MM)",     s.get("post_time", "18:00"),    False),
        ]
        for key, label, value, masked in rows:
            self._make_field(panel, key, label, value, masked)
        return panel

    def _build_appearance(self, parent):
        panel = tk.Frame(parent, bg=BG)
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        tk.Label(body, text="VerdictIn60 Dark", font=("Helvetica", 11, "bold"),
                 fg=WHITE, bg=CARD, anchor="w").pack(fill="x")
        tk.Label(
            body,
            text="The official black / crimson VerdictIn60 theme is applied across the whole app. "
                 "There are no other themes to switch between yet.",
            font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            wraplength=520, justify="left",
        ).pack(fill="x", pady=(4, 0))
        return panel

    def _build_ai(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "AI  —  OLLAMA SETTINGS")
        tk.Label(panel, text="AI SPEED MODE", font=("Helvetica", 8, "bold"),
                 fg=TEXT_SECONDARY, bg=BG, anchor="w", justify="left").pack(fill="x", pady=(4, 3))
        ai_speed_options = ["Fast", "Balanced", "Best Accuracy"]
        current_speed = s.get("ai_speed_mode", "")
        if current_speed not in AI_SPEED_MODES:
            current_ai = s.get("ai_model", "qwen3:14b")
            current_speed = "Best Accuracy" if current_ai == "qwen3:32b" else "Balanced"
        self._ai_speed_var = tk.StringVar(value=current_speed or "Balanced")
        ai_dropdown = ttk.Combobox(
            panel, textvariable=self._ai_speed_var,
            values=ai_speed_options, state="readonly",
            font=("Helvetica", 11)
        )
        ai_dropdown.pack(fill="x", ipady=4)
        return panel

    def _build_models(self, parent):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "MODELS USED BY EACH SPEED MODE")
        for mode, cfg in AI_SPEED_MODES.items():
            card = make_card(panel)
            card.pack(fill="x", pady=(0, 8))
            body = card_body(card)
            tk.Label(body, text=mode, font=("Helvetica", 10, "bold"),
                     fg=WHITE, bg=CARD, anchor="w").pack(fill="x")
            tk.Label(
                body,
                text=f"Identify: {cfg.get('identify', '—')}   ·   Caption: {cfg.get('caption', '—')}"
                     f"   ·   Verify: {cfg.get('verify', '—')}",
                font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            ).pack(fill="x", pady=(2, 0))
        return panel

    def _build_verification(self, parent):
        panel = tk.Frame(parent, bg=BG)
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        tk.Label(body, text="Source Verification", font=("Helvetica", 11, "bold"),
                 fg=WHITE, bg=CARD, anchor="w").pack(fill="x")
        tk.Label(
            body,
            text="Every imported case is checked against independent sources before a caption "
                 "is finalized. Verification runs automatically during import and export and has "
                 "no user-configurable options yet.",
            font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            wraplength=520, justify="left",
        ).pack(fill="x", pady=(4, 0))
        return panel

    def _build_exports(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "INTERNET ARCHIVE  —  VIDEO HOSTING")
        rows = [
            ("ia_access_key", "IA Access Key", s.get("ia_access_key", ""), False),
            ("ia_secret_key", "IA Secret Key", s.get("ia_secret_key", ""), True),
        ]
        for key, label, value, masked in rows:
            self._make_field(panel, key, label, value, masked)
        return panel

    def _build_advanced(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "PREFERRED BROWSER FOR COOKIES")
        browser_options = ["chrome", "safari", "firefox"]
        self._browser_var = tk.StringVar(value=s.get("preferred_browser", "chrome"))
        browser_dropdown = ttk.Combobox(
            panel, textvariable=self._browser_var,
            values=browser_options, state="readonly",
            font=("Helvetica", 11)
        )
        browser_dropdown.pack(fill="x", ipady=4)
        return panel

    # ── Shared field widget ───────────────────────────────────────────────────

    def _make_field(self, parent, key, label, value, masked):
        tk.Label(parent, text=label.upper(), font=("Helvetica", 8, "bold"),
                 fg=TEXT_SECONDARY, bg=BG, anchor="w", justify="left").pack(fill="x", pady=(10, 3))
        e = tk.Entry(parent, show="*" if masked else "",
                     font=("Helvetica", 11), fg=WHITE, bg=INPUT_BG,
                     insertbackground=WHITE, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
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
