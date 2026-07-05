"""Research Hub tab — multi-clue AI case identification, budgeted source
research, and archive recovery, built on verdictin60_core.research_hub.

Self-contained like case_library.LibraryTab: build_research_hub_tab() just
instantiates ResearchHubTab and stores it on the app for _switch_tab to reuse.
"""
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog

import tkinter as tk
from tkinter import ttk

from verdictin60_core import research_hub
from verdictin60_ui.theme import (
    BG, CARD, CARD_ALT, BORDER, TEXT, TEXT_MUTED, TEXT_SECONDARY,
    ACCENT, ACCENT_HOT, INPUT_BG, DISABLED,
    FONT_FAMILY, FONT_MONO, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG,
)
from verdictin60_ui.components import (
    make_card, card_body, make_badge, make_confidence_badge,
    make_loading_state, stop_loading_state, make_error_banner, make_empty_state,
)
from verdictin60_ui.widgets import _make_lbtn, _lbtn_disable, _lbtn_enable

PAD = 30


def _field_label(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=TEXT_MUTED,
                     font=(FONT_FAMILY, 10, "bold"))


def build_research_hub_tab(app, parent):
    app._research_tab = ResearchHubTab(parent, app._library)


class ResearchHubTab:
    def __init__(self, parent, library):
        self.parent = parent
        self.library = library
        self._result = None
        self._running = False
        self._build_ui()

    # ── UI scaffold ───────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = tk.Frame(self.parent, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
        inner_win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(inner_win, width=e.width)

        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", _on_resize)
        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Enter>", lambda e: canvas.bind_all(
            "<MouseWheel>", lambda ev: canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self._inner = inner

        tk.Label(inner, text="RESEARCH HUB", bg=BG, fg=TEXT,
                 font=(FONT_FAMILY, 16, "bold")).pack(anchor="w", padx=PAD, pady=(SPACE_LG - 4, 0))
        tk.Label(
            inner,
            text=("Paste any combination of names, locations, dates, keywords, a headline, or a "
                  "platform URL. Investigate identifies the most likely case, researches official "
                  "and reporting sources, and recovers archived copies of anything blocked."),
            bg=BG, fg=TEXT_MUTED, font=(FONT_FAMILY, 10), wraplength=760, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(4, SPACE_MD))

        # ── Search panel ──────────────────────────────────────────────────────
        _field_label(inner, "CLUES").pack(anchor="w", padx=PAD, pady=(0, SPACE_XS))
        clue_frame = tk.Frame(inner, bg=INPUT_BG, highlightthickness=1, highlightbackground=BORDER)
        clue_frame.pack(fill="x", padx=PAD)
        self._clue_text = tk.Text(
            clue_frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            font=(FONT_MONO, 12), bd=0, relief="flat", highlightthickness=0,
            wrap="word", height=6,
        )
        self._clue_text.pack(fill="x", padx=10, pady=10)

        self._btn_investigate = _make_lbtn(
            inner, "INVESTIGATE", self._start_investigate,
            bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT,
            font=(FONT_FAMILY, 14, "bold"), pady=16,
        )
        self._btn_investigate.pack(padx=PAD, pady=(SPACE_SM, 0), fill="x")

        self._error_host = tk.Frame(inner, bg=BG)
        self._error_host.pack(fill="x", padx=PAD)

        self._status_host = tk.Frame(inner, bg=BG)
        self._status_host.pack(fill="x", padx=PAD, pady=(SPACE_SM, 0))

        # ── Results host (rebuilt after every investigation) ─────────────────
        self._results_host = tk.Frame(inner, bg=BG)
        self._results_host.pack(fill="both", expand=True, padx=PAD, pady=(SPACE_LG - 6, SPACE_LG))
        make_empty_state(
            self._results_host,
            "No investigation yet.\n\nPaste some clues above and click Investigate.",
            bg=BG,
        ).pack(pady=60)

    def _set_status(self, text, error=False):
        for child in self._status_host.winfo_children():
            child.destroy()
        for child in self._error_host.winfo_children():
            child.destroy()
        if error:
            make_error_banner(self._error_host, text, title="Research Hub").pack(fill="x", pady=(SPACE_SM, 0))
            return
        if text:
            tk.Label(self._status_host, text=text, bg=BG, fg=TEXT_SECONDARY,
                     font=(FONT_FAMILY, 10)).pack(anchor="w")

    # ── Investigate ───────────────────────────────────────────────────────────

    def _start_investigate(self):
        if self._running:
            return
        raw = self._clue_text.get("1.0", "end").strip()
        if not raw:
            self._set_status("Paste at least one clue — a name, URL, location, date, or keyword.", error=True)
            return
        self._running = True
        _lbtn_disable(self._btn_investigate, DISABLED, TEXT_MUTED)
        self._set_status("")
        self._set_status("⏳  Investigating — identifying the case and researching sources…")
        for child in self._results_host.winfo_children():
            child.destroy()
        self._loading = make_loading_state(self._results_host, "Investigating…", bg=BG)
        self._loading.pack(pady=40)
        threading.Thread(target=self._run_investigate, args=(raw,), daemon=True).start()

    def _run_investigate(self, raw: str):
        try:
            result = research_hub.investigate(raw)
        except Exception as e:
            self.parent.after(0, lambda: self._on_investigate_error(str(e)))
            return
        self.parent.after(0, lambda: self._on_investigate_done(result))

    def _on_investigate_error(self, message: str):
        self._running = False
        _lbtn_enable(self._btn_investigate, ACCENT, TEXT, hover_bg=ACCENT_HOT)
        stop_loading_state(self._loading)
        for child in self._results_host.winfo_children():
            child.destroy()
        self._set_status(f"Investigation failed: {message}", error=True)

    def _on_investigate_done(self, result: dict):
        self._running = False
        _lbtn_enable(self._btn_investigate, ACCENT, TEXT, hover_bg=ACCENT_HOT)
        stop_loading_state(self._loading)
        self._result = result
        case = result.get("case", {})
        if not case.get("case_title"):
            self._set_status(
                "No case could be identified from those clues — try adding a name, "
                "location, date, or a more specific URL.", error=True,
            )
        elif case.get("fallback"):
            self._set_status("Investigation complete (AI identification unavailable — used clues directly).")
        else:
            self._set_status("Investigation complete.")
        self._render_results(result)

    # ── Results rendering ─────────────────────────────────────────────────────

    def _render_results(self, result: dict):
        for child in self._results_host.winfo_children():
            child.destroy()
        case = result.get("case", {})
        sources = result.get("sources", [])
        stats = result.get("stats", {})

        if not case.get("case_title"):
            make_empty_state(
                self._results_host,
                "No case identified.\n\nAdd more specific clues (a full name, exact location, "
                "or a direct link) and try again.",
                bg=BG,
            ).pack(pady=60)
            return

        # ── Case summary card ─────────────────────────────────────────────────
        summary = make_card(self._results_host, padx=18, pady=16)
        summary.pack(fill="x", pady=(0, SPACE_MD))
        body = card_body(summary)

        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text=case["case_title"], bg=CARD, fg=TEXT,
                 font=(FONT_FAMILY, 15, "bold"), anchor="w", wraplength=560,
                 justify="left").pack(side="left", fill="x", expand=True)
        make_confidence_badge(head, case.get("confidence", "Very Low"),
                              case.get("confidence_reason")).pack(side="right", anchor="n")

        if case.get("aliases"):
            tk.Label(body, text="Also known as: " + ", ".join(case["aliases"]),
                     bg=CARD, fg=TEXT_MUTED, font=(FONT_FAMILY, 9),
                     wraplength=680, justify="left").pack(anchor="w", pady=(SPACE_SM, 0))

        for label, key in (("Victims", "victims"), ("Suspects", "suspects"),
                          ("Related people", "related_people")):
            values = case.get(key) or []
            if values:
                tk.Label(body, text=f"{label}: {', '.join(values)}", bg=CARD, fg=TEXT_SECONDARY,
                         font=(FONT_FAMILY, 9), wraplength=680, justify="left").pack(anchor="w", pady=(4, 0))

        if case.get("timeline"):
            tk.Label(body, text="Timeline:", bg=CARD, fg=TEXT,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(SPACE_SM, 0))
            for event in case["timeline"][:12]:
                tk.Label(body, text=f"• {event}", bg=CARD, fg=TEXT_SECONDARY,
                         font=(FONT_FAMILY, 9), wraplength=680, justify="left",
                         anchor="w").pack(anchor="w")

        if case.get("outcome"):
            tk.Label(body, text=f"Outcome: {case['outcome']}", bg=CARD, fg=TEXT_SECONDARY,
                     font=(FONT_FAMILY, 9), wraplength=680, justify="left").pack(anchor="w", pady=(SPACE_SM, 0))

        # ── Stats line: elapsed / checked / skipped / stopped_reason ─────────
        stats_parts = [f"{result.get('elapsed_seconds', 0)}s elapsed",
                       f"{stats.get('sources_checked', 0)} sources checked"]
        if stats.get("skipped_slow_or_blocked"):
            stats_parts.append(f"{stats['skipped_slow_or_blocked']} slow/blocked source(s) skipped")
        if stats.get("stopped_reason"):
            stats_parts.append(f"stopped: {stats['stopped_reason']}")
        tk.Label(body, text="  •  ".join(stats_parts), bg=CARD, fg=TEXT_MUTED,
                 font=(FONT_FAMILY, 8), wraplength=680, justify="left").pack(anchor="w", pady=(SPACE_SM, 0))

        # ── Grouped sources ────────────────────────────────────────────────────
        blocked = [s for s in sources if s.get("blocked") and s.get("tier") != "Wikipedia"]
        archived = [s for s in blocked if s.get("archived")]
        not_archived = [s for s in blocked if not s.get("archived")]
        official = [s for s in sources if not s.get("blocked") and s.get("kind") in ("Official", "Agency")]
        reporting = [s for s in sources if not s.get("blocked")
                    and s.get("kind") in ("Reporting", "Investigative") and s.get("tier") != "Wikipedia"]

        self._source_group(self._results_host, "Official Sources", official)
        self._source_group(self._results_host, "Reporting (Accessible)", reporting)
        self._source_group(self._results_host, "Reporting (Archived)", archived, archived=True)
        self._source_group(self._results_host, "Blocked / Inaccessible", not_archived, blocked_group=True)

        # ── Actions ────────────────────────────────────────────────────────────
        actions = tk.Frame(self._results_host, bg=BG)
        actions.pack(fill="x", pady=(SPACE_MD, 0))
        action_defs = [
            ("Save to Case Library", self._action_save_to_library),
            ("Generate Caption", self._action_generate_caption),
            ("Copy All Sources", self._action_copy_all_sources),
            ("Copy Archive Links", self._action_copy_archive_links),
            ("Open All Sources", self._action_open_all_sources),
            ("Export Markdown", self._action_export_markdown),
        ]
        for i, (label, cmd) in enumerate(action_defs):
            btn = _make_lbtn(
                actions, label, cmd, bg=INPUT_BG, fg=TEXT_MUTED,
                hover_bg=BORDER, hover_fg=TEXT, font=(FONT_FAMILY, 9, "bold"),
                pady=9, padx=12,
            )
            btn.grid(row=i // 3, column=i % 3, padx=(0, 8), pady=(0, 8), sticky="ew")
        for col in range(3):
            actions.grid_columnconfigure(col, weight=1)

    def _source_group(self, parent, heading, items, archived=False, blocked_group=False):
        if not items:
            return
        card = make_card(parent, padx=14, pady=12, hover=False)
        card.pack(fill="x", pady=(0, SPACE_SM))
        body = card_body(card)
        tk.Label(body, text=f"{heading} ({len(items)})", bg=CARD, fg=TEXT,
                 font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, SPACE_XS))
        for src in items:
            row = tk.Frame(body, bg=CARD_ALT)
            row.pack(fill="x", pady=1)
            inner = tk.Frame(row, bg=CARD_ALT)
            inner.pack(fill="x", padx=8, pady=5)
            make_badge(inner, src.get("kind", "Source"),
                      status="neutral" if not blocked_group else "error").pack(side="left", padx=(0, SPACE_SM))
            title = src.get("title") or src.get("url", "")
            detail_lines = [f"{title}", src.get("url", "")]
            if archived and src.get("archive_url"):
                detail_lines.append(f"Archived via {src.get('archive_provider', 'archive')}: {src['archive_url']}")
            elif blocked_group:
                if src.get("manual_archive_links"):
                    links = ", ".join(f"{name}" for name in src["manual_archive_links"])
                    detail_lines.append(f"Reason: {src.get('inaccessible_reason', 'Inaccessible')} — manual archive lookup: {links}")
                else:
                    detail_lines.append(f"Reason: {src.get('inaccessible_reason', 'Inaccessible')}")
            if src.get("is_pdf"):
                detail_lines.append("PDF source")
            tk.Label(inner, text="\n".join(l for l in detail_lines if l), bg=CARD_ALT, fg=TEXT_MUTED,
                     font=(FONT_FAMILY, 8), wraplength=620, justify="left", anchor="w").pack(
                     side="left", fill="x", expand=True)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _accessible_sources(self) -> list:
        if not self._result:
            return []
        return [s for s in self._result.get("sources", [])
                if not s.get("blocked") and s.get("tier") != "Wikipedia"]

    def _blocked_sources(self) -> list:
        if not self._result:
            return []
        return [s for s in self._result.get("sources", [])
                if s.get("blocked") and s.get("tier") != "Wikipedia"]

    def _copy_to_clipboard(self, text: str):
        self.parent.clipboard_clear()
        self.parent.clipboard_append(text)

    def _action_save_to_library(self):
        if not self._result:
            return
        case = self._result["case"]
        title = case.get("case_title")
        if not title:
            return
        clues = self._result.get("clues", {})
        source_url = clues["urls"][0] if clues.get("urls") else ""
        try:
            self.library.save_case(case_name=title, status="Draft", source_url=source_url)
            self._set_status(f"Saved “{title}” to the Case Library.")
        except Exception as e:
            self._set_status(f"Save to Case Library failed: {e}", error=True)

    def _action_generate_caption(self):
        if not self._result or not self._result["case"].get("case_title"):
            return
        self._set_status("⏳  Generating caption…")

        def _run():
            try:
                caption = research_hub.generate_caption(self._result)
            except Exception as e:
                self.parent.after(0, lambda: self._set_status(f"Caption generation failed: {e}", error=True))
                return
            self.parent.after(0, lambda: self._show_caption_dialog(caption))
        threading.Thread(target=_run, daemon=True).start()

    def _show_caption_dialog(self, caption: str):
        self._set_status("Caption generated.")
        win = tk.Toplevel(self.parent)
        win.title("Generated Caption — Research Hub")
        win.configure(bg=BG)
        win.geometry("620x520")
        text_frame = tk.Frame(win, bg=INPUT_BG, highlightthickness=1, highlightbackground=BORDER)
        text_frame.pack(fill="both", expand=True, padx=16, pady=16)
        text_widget = tk.Text(text_frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                              font=(FONT_FAMILY, 11), bd=0, relief="flat", wrap="word")
        text_widget.pack(fill="both", expand=True, padx=10, pady=10)
        text_widget.insert("1.0", caption)
        _make_lbtn(
            win, "COPY CAPTION", lambda: self._copy_to_clipboard(text_widget.get("1.0", "end").strip()),
            bg=ACCENT, fg=TEXT, hover_bg=ACCENT_HOT, font=(FONT_FAMILY, 11, "bold"), pady=10,
        ).pack(fill="x", padx=16, pady=(0, 16))

    def _action_copy_all_sources(self):
        sources = self._accessible_sources() + self._blocked_sources()
        if not sources:
            self._set_status("No sources to copy yet.", error=True)
            return
        lines = [f"{s.get('title', s['url'])} — {s['url']}" for s in sources]
        self._copy_to_clipboard("\n".join(lines))
        self._set_status(f"Copied {len(lines)} source(s) to the clipboard.")

    def _action_copy_archive_links(self):
        blocked = self._blocked_sources()
        lines = []
        for s in blocked:
            if s.get("archive_url"):
                lines.append(f"{s.get('title', s['url'])} — {s['archive_url']}")
            for name, link in (s.get("manual_archive_links") or {}).items():
                lines.append(f"{s.get('title', s['url'])} ({name}) — {link}")
        if not lines:
            self._set_status("No archive links available yet.", error=True)
            return
        self._copy_to_clipboard("\n".join(lines))
        self._set_status(f"Copied {len(lines)} archive link(s) to the clipboard.")

    def _action_open_all_sources(self):
        sources = self._accessible_sources()[:15]
        if not sources:
            self._set_status("No accessible sources to open yet.", error=True)
            return
        for s in sources:
            webbrowser.open(s["url"])
        self._set_status(f"Opened {len(sources)} source(s) in your browser.")

    def _action_export_markdown(self):
        if not self._result:
            return
        try:
            markdown = research_hub.export_markdown(self._result)
        except Exception as e:
            self._set_status(f"Export failed: {e}", error=True)
            return
        title = self._result["case"].get("case_title") or "research"
        safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip() or "research"
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=f"{safe_name}.md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(markdown, encoding="utf-8")
            self._set_status(f"Exported research to {path}")
        except Exception as e:
            self._set_status(f"Export failed: {e}", error=True)
