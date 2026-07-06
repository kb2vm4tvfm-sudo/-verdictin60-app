import platform
import tkinter as tk
from tkinter import ttk

from verdictin60_core.settings import load_settings, save_settings
from verdictin60_core.ai import AI_SPEED_MODES, NVIDIA_TASK_FIELDS, get_nvidia_status
from verdictin60_core import provider_guard
from verdictin60_ui.widgets import BG, CRIMSON, CRIMSON_HOT, WHITE, LIGHT_GRAY, _make_lbtn
from verdictin60_ui.theme import CARD, BORDER, TEXT_MUTED, INPUT_BG, SPACE_MD
from verdictin60_ui.components import (
    make_segmented_tabs, make_card, card_body, make_badge, make_setting_row,
)

SETTINGS_TABS = [
    ("general", "General"),
    ("appearance", "Appearance"),
    ("ai", "AI"),
    ("models", "Models"),
    ("exports", "Exports"),
    ("advanced", "Advanced"),
]

AI_PROVIDER_MODE_LABELS = {
    "Local only": "Local only — Ollama",
    "Cloud fallback": "Cloud fallback — Ollama first, NVIDIA NIM if Ollama fails",
    "Cloud only": "Cloud only — NVIDIA NIM",
}
AI_PROVIDER_LABEL_TO_MODE = {v: k for k, v in AI_PROVIDER_MODE_LABELS.items()}


class SettingsDialog(tk.Toplevel):
    # Provider status label -> make_badge() status key.
    _STATUS_BADGE = {
        "Active": "success",
        "Missing key": "neutral",
        "Rate limited": "warning",
        "Quota reached": "error",
        "Disabled": "error",
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, True)

        s = load_settings()
        self._vars = {}
        self._bool_vars = {}
        self._style = self._build_combobox_style()

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

        # Sub-tab content is wrapped in a scrollable canvas so panels taller
        # than the dialog (e.g. AI with its provider/safety/advanced cards)
        # can still be reached on smaller windows, instead of being clipped
        # by the fixed-size Toplevel with no way to reach the rest.
        scroll_wrap = tk.Frame(self, bg=BG)
        scroll_wrap.pack(fill="both", expand=True, padx=30, pady=(14, 0))
        panels_canvas = tk.Canvas(scroll_wrap, bg=BG, highlightthickness=0)
        panels_scrollbar = ttk.Scrollbar(
            scroll_wrap, orient="vertical", command=panels_canvas.yview)
        panels_canvas.configure(yscrollcommand=panels_scrollbar.set)
        panels_scrollbar.pack(side="right", fill="y")
        panels_canvas.pack(side="left", fill="both", expand=True)

        panels_host = tk.Frame(panels_canvas, bg=BG)
        panels_win = panels_canvas.create_window((0, 0), window=panels_host, anchor="nw")

        def _on_canvas_configure(e):
            panels_canvas.itemconfig(panels_win, width=e.width)

        def _on_panels_configure(_e):
            panels_canvas.configure(scrollregion=panels_canvas.bbox("all"))

        panels_canvas.bind("<Configure>", _on_canvas_configure)
        panels_host.bind("<Configure>", _on_panels_configure)
        self._bind_mousewheel(panels_canvas)

        active_speed_mode = self._resolve_speed_mode(s)

        self._panels = {
            "general":      self._build_general(panels_host, s),
            "appearance":   self._build_appearance(panels_host),
            "ai":           self._build_ai(panels_host, active_speed_mode),
            "models":       self._build_models(panels_host, active_speed_mode),
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
        dw, dh = 660, 660
        self.geometry(f"{dw}x{dh}+{px+(pw-dw)//2}+{py+(ph-dh)//2}")

    # ── One-time setup ───────────────────────────────────────────────────────

    def _bind_mousewheel(self, canvas):
        """Cross-platform wheel / trackpad scrolling for the settings panel.

        Bound on the whole dialog (not just the canvas) for as long as it's
        open: this is a modal Toplevel (grab_set()), so there's no other
        window competing for wheel events, and binding at that level means
        scrolling keeps working no matter which child widget (label, card,
        entry, dropdown, or empty space) the cursor happens to be over.
        Windows/Linux report delta in multiples of 120; macOS Aqua reports
        small raw deltas, so it needs its own scale factor. Linux/X11 can
        also deliver wheel as Button-4/5 clicks instead of MouseWheel.
        """
        is_mac = platform.system() == "Darwin"

        def _on_wheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            elif is_mac:
                canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.bind_all("<MouseWheel>", _on_wheel)
        self.bind_all("<Button-4>", _on_wheel)
        self.bind_all("<Button-5>", _on_wheel)
        self.bind("<Destroy>", self._unbind_mousewheel)

    def _unbind_mousewheel(self, event):
        if event.widget is not self:
            return
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _build_combobox_style(self):
        """A dropdown style scoped to this dialog only (named style, so it
        never touches the default TCombobox look used elsewhere, e.g.
        case_library.py's status dropdown)."""
        style = ttk.Style(self)
        style.configure(
            "VerdictIn60.TCombobox",
            fieldbackground=INPUT_BG, background=INPUT_BG, foreground=WHITE,
            arrowcolor=TEXT_MUTED, bordercolor=BORDER,
            lightcolor=INPUT_BG, darkcolor=INPUT_BG,
        )
        style.map(
            "VerdictIn60.TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", WHITE)],
            selectbackground=[("readonly", INPUT_BG)],
            selectforeground=[("readonly", WHITE)],
        )
        return style

    def _resolve_speed_mode(self, s):
        current_speed = s.get("ai_speed_mode", "")
        if current_speed not in AI_SPEED_MODES:
            current_ai = s.get("ai_model", "qwen3:14b")
            current_speed = "Best Accuracy" if current_ai == "qwen3:32b" else "Balanced"
        return current_speed or "Balanced"

    # ── Panel builders ────────────────────────────────────────────────────────

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=("Helvetica", 8, "bold"),
                 fg=CRIMSON, bg=BG, anchor="w").pack(fill="x", pady=(0, 6))

    def _build_general(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "BUFFER")
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        fields = [
            ("buffer_key", "Buffer API Key",
             "Authenticates VerdictIn60 with the Buffer API when scheduling posts.",
             s.get("buffer_key", ""), True),
            ("buffer_channel_id", "Buffer Instagram Channel ID",
             "The Buffer channel connected to the destination Instagram account.",
             s.get("buffer_channel_id", ""), False),
            ("post_time", "Daily Post Time (HH:MM)",
             "Local time each scheduled case is posted through Buffer.",
             s.get("post_time", "18:00"), False),
        ]
        self._make_field_rows(body, fields)
        return panel

    def _build_appearance(self, parent):
        panel = tk.Frame(parent, bg=BG)
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="VerdictIn60 Dark", font=("Helvetica", 11, "bold"),
                 fg=WHITE, bg=CARD, anchor="w").pack(side="left")
        make_badge(head, "ACTIVE", status="success").pack(side="left", padx=(8, 0))
        tk.Label(
            body,
            text="The official black / crimson VerdictIn60 theme is applied across the whole app. "
                 "There are no other themes to switch between yet.",
            font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            wraplength=520, justify="left",
        ).pack(fill="x", pady=(6, 0))
        return panel

    def _build_ai(self, parent, active_speed_mode):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "AI  —  OLLAMA SETTINGS")
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        row = make_setting_row(
            body, "AI Speed Mode",
            "Controls which Ollama models are used to identify, caption, and verify cases.",
        )
        row.pack(fill="x")
        ai_speed_options = ["Fast", "Balanced", "Best Accuracy"]
        self._ai_speed_var = tk.StringVar(value=active_speed_mode)
        ai_dropdown = ttk.Combobox(
            row, textvariable=self._ai_speed_var,
            values=ai_speed_options, state="readonly",
            font=("Helvetica", 11), style="VerdictIn60.TCombobox",
        )
        ai_dropdown.pack(fill="x", ipady=4)

        self._section_label(panel, "AI PROVIDER  —  OPTIONAL NVIDIA NIM CLOUD FALLBACK")
        provider_card = make_card(panel)
        provider_card.pack(fill="x", pady=(SPACE_MD, 0))
        provider_body = card_body(provider_card)
        provider_row = make_setting_row(
            provider_body, "AI Provider",
            "Ollama runs locally and stays free by default. NVIDIA NIM is an optional "
            "free cloud fallback — nothing is sent to NVIDIA unless you pick a Cloud "
            "option here and add an API key below.",
        )
        provider_row.pack(fill="x")
        s = load_settings()
        current_mode = s.get("ai_provider_mode", "Local only")
        if current_mode not in AI_PROVIDER_MODE_LABELS:
            current_mode = "Local only"
        self._ai_provider_var = tk.StringVar(value=AI_PROVIDER_MODE_LABELS[current_mode])
        provider_dropdown = ttk.Combobox(
            provider_row, textvariable=self._ai_provider_var,
            values=list(AI_PROVIDER_MODE_LABELS.values()), state="readonly",
            font=("Helvetica", 11), style="VerdictIn60.TCombobox",
        )
        provider_dropdown.pack(fill="x", ipady=4)

        tk.Frame(provider_body, bg=BORDER, height=1).pack(fill="x", pady=(SPACE_MD, SPACE_MD))
        key_row = make_setting_row(
            provider_body, "NVIDIA API Key",
            "From build.nvidia.com. Stored locally, masked on screen, and never logged. "
            "Leave blank to keep using Ollama only.",
        )
        key_row.pack(fill="x")
        self._make_entry(key_row, "nvidia_api_key", s.get("nvidia_api_key", ""), True)

        self._section_label(panel, "SAFETY  —  COST / QUOTA GUARD")
        safety_card = make_card(panel)
        safety_card.pack(fill="x", pady=(SPACE_MD, 0))
        safety_body = card_body(safety_card)
        tk.Label(
            safety_body,
            text="Stops calling a cloud provider for the rest of this session after it reports "
                 "a quota, billing, rate-limit, or access error, so VerdictIn60 never loops "
                 "into unexpected charges. Ollama and local-only mode are never affected.",
            font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            wraplength=520, justify="left",
        ).pack(fill="x", pady=(0, SPACE_MD))
        self._make_checkbox(
            safety_body, "cloud_spending_guard",
            "Cloud/service spending guard", bool(s.get("cloud_spending_guard", True)),
        )
        self._make_checkbox(
            safety_body, "disable_provider_after_first_error",
            "Disable provider after first quota/billing/rate-limit error",
            bool(s.get("disable_provider_after_first_error", True)),
        )
        tk.Frame(safety_body, bg=BORDER, height=1).pack(fill="x", pady=(SPACE_MD, SPACE_MD))
        status_row = tk.Frame(safety_body, bg=CARD)
        status_row.pack(fill="x")
        tk.Label(status_row, text="NVIDIA:", font=("Helvetica", 9, "bold"),
                 fg=WHITE, bg=CARD, anchor="w").pack(side="left")
        nvidia_status = get_nvidia_status()
        make_badge(
            status_row, nvidia_status, status=self._STATUS_BADGE.get(nvidia_status, "neutral")
        ).pack(side="left", padx=(8, 0))

        self._section_label(panel, "ADVANCED  —  PER-TASK NVIDIA MODELS (OPTIONAL)")
        advanced_card = make_card(panel)
        advanced_card.pack(fill="x", pady=(SPACE_MD, 0))
        advanced_body = card_body(advanced_card)
        tk.Label(
            advanced_body,
            text="Override the NVIDIA NIM model used for individual tasks. All tasks share the "
                 "NVIDIA API key above. Leave a field blank to use the app default for that task.",
            font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            wraplength=520, justify="left",
        ).pack(fill="x", pady=(0, SPACE_MD))
        advanced_fields = [
            (f"nvidia_model_{task}", label, f"Default: {default}", s.get(f"nvidia_model_{task}", ""), False)
            for task, label, default in NVIDIA_TASK_FIELDS
        ]
        self._make_field_rows(advanced_body, advanced_fields)
        return panel

    def _build_models(self, parent, active_speed_mode):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "MODELS USED BY EACH SPEED MODE")
        for mode, cfg in AI_SPEED_MODES.items():
            card = make_card(panel)
            card.pack(fill="x", pady=(0, 8))
            body = card_body(card)
            head = tk.Frame(body, bg=CARD)
            head.pack(fill="x")
            tk.Label(head, text=mode, font=("Helvetica", 10, "bold"),
                     fg=WHITE, bg=CARD, anchor="w").pack(side="left")
            if mode == active_speed_mode:
                make_badge(head, "CURRENT", status="info").pack(side="left", padx=(8, 0))
            tk.Label(
                body,
                text=f"Identify: {cfg.get('identify', '—')}   ·   Caption: {cfg.get('caption', '—')}"
                     f"   ·   Verify: {cfg.get('verify', '—')}",
                font=("Helvetica", 9), fg=TEXT_MUTED, bg=CARD, anchor="w",
            ).pack(fill="x", pady=(4, 0))
        return panel

    def _build_exports(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "INTERNET ARCHIVE  —  VIDEO HOSTING")
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        fields = [
            ("ia_access_key", "IA Access Key",
             "Public access key used to upload finished reels to Internet Archive.",
             s.get("ia_access_key", ""), False),
            ("ia_secret_key", "IA Secret Key",
             "Secret key paired with the access key above. Kept masked on screen.",
             s.get("ia_secret_key", ""), True),
        ]
        self._make_field_rows(body, fields)
        return panel

    def _build_advanced(self, parent, s):
        panel = tk.Frame(parent, bg=BG)
        self._section_label(panel, "PREFERRED BROWSER FOR COOKIES")
        card = make_card(panel)
        card.pack(fill="x")
        body = card_body(card)
        row = make_setting_row(
            body, "Browser",
            "Browser VerdictIn60 reads cookies from when importing sources that require a login.",
        )
        row.pack(fill="x")
        browser_options = ["chrome", "safari", "firefox"]
        self._browser_var = tk.StringVar(value=s.get("preferred_browser", "chrome"))
        browser_dropdown = ttk.Combobox(
            row, textvariable=self._browser_var,
            values=browser_options, state="readonly",
            font=("Helvetica", 11), style="VerdictIn60.TCombobox",
        )
        browser_dropdown.pack(fill="x", ipady=4)
        return panel

    # ── Shared field widgets ──────────────────────────────────────────────────

    def _make_field_rows(self, body, fields):
        """Render a list of (key, label, description, value, masked) settings
        as label + description + entry rows, with a divider between rows."""
        for i, (key, label, description, value, masked) in enumerate(fields):
            if i > 0:
                tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(0, SPACE_MD))
            row = make_setting_row(body, label, description)
            row.pack(fill="x")
            self._make_entry(row, key, value, masked)

    def _make_checkbox(self, parent, key, label, value):
        var = tk.BooleanVar(value=value)
        cb = tk.Checkbutton(
            parent, text=label, variable=var, onvalue=True, offvalue=False,
            font=("Helvetica", 10), fg=WHITE, bg=CARD, activebackground=CARD,
            activeforeground=WHITE, selectcolor=INPUT_BG,
            highlightthickness=0, bd=0, anchor="w",
        )
        cb.pack(fill="x", anchor="w", pady=(0, 4))
        self._bool_vars[key] = var

    def _make_entry(self, parent, key, value, masked):
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
        current.update({k: bool(v.get()) for k, v in self._bool_vars.items()})
        speed_mode = self._ai_speed_var.get().strip()
        if speed_mode not in AI_SPEED_MODES:
            speed_mode = "Balanced"
        current["ai_speed_mode"] = speed_mode
        current["ai_model"] = AI_SPEED_MODES[speed_mode]["caption"]
        provider_label = self._ai_provider_var.get().strip()
        current["ai_provider_mode"] = AI_PROVIDER_LABEL_TO_MODE.get(provider_label, "Local only")
        current["preferred_browser"] = self._browser_var.get().strip()
        save_settings(current)
        # Quota/billing and auth disables last "until app restart or settings
        # change" per the cost/quota safety guard rules — saving Settings is
        # that explicit "try again" signal. Rate-limit cooldowns are strictly
        # time-based and are left alone.
        provider_guard.clear_settings_triggered_disables("nvidia")
        self.destroy()
