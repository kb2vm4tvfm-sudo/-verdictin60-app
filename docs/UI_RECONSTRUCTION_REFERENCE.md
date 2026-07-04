# UI Reconstruction Reference

## Purpose

This document translates UI/UX guidance from a Base44-generated React web app concept
(internally referred to as "CODE BASE 44") into design direction VerdictIn60 can use.

**Base44 is visual and structural inspiration only.** It is not a spec to implement
literally, and it does not change what VerdictIn60 is:

- VerdictIn60 **remains a Python/Tkinter desktop app**. It does not become a web app,
  and it is not being ported to React, Vue, or any browser framework.
- Nothing in this document authorizes editing app code, changing functionality, or
  restyling existing screens. It is reference material for **future** UI work, to be
  applied deliberately and incrementally, screen by screen, when explicitly requested.
- Where the Base44 concept assumes things VerdictIn60 does not have or want (hosted
  auth, a router, a cyan/blue SaaS theme, GPT-4o branding, Base44 SDK calls), those
  parts are called out as **not applicable** rather than adapted.

Read this alongside `docs/AI_RULES.md` (UI Rules section) and `docs/ARCHITECTURE.md`
before making any UI change. If this document and `AI_RULES.md` ever conflict,
`AI_RULES.md` wins.

## Visual Principles From Base44

The Base44 concept is a dark-themed, data-dense SaaS dashboard. The principles worth
carrying forward — as *ideas*, translated into VerdictIn60's own black/crimson theme,
not its cyan/blue palette — are:

- **Dark surface hierarchy.** Distinct layers for app background, sidebar, cards, and
  hover/active states, rather than one flat background. VerdictIn60's `theme.py`
  already does this (`BG` → `SIDEBAR_BG` → `CARD` → `CARD_ALT` → `CARD_HOVER`).
- **One accent color, used sparingly.** Base44 reserves its accent (cyan/blue) for
  active nav state, primary buttons, and focus rings — not for general decoration.
  VerdictIn60's equivalent is its single crimson `ACCENT`, which must stay reserved
  the same way (see `theme.py` docstring).
- **Semantic status colors stay separate from the brand accent.** Verified/Needs
  Review/Not Verified use green/amber/red in Base44, never the brand color. VerdictIn60
  already encodes this via `SUCCESS`/`WARNING`/`ERROR` in `theme.py`, kept distinct from
  `ACCENT`.
- **Muted secondary text, sparing bold.** Titles are bold and bright; supporting text
  (timestamps, source names, helper copy) is a muted gray one or two steps down from
  primary text — matching `TEXT` vs. `TEXT_SECONDARY`/`TEXT_MUTED`/`TEXT_DIM`.
  Base44's own font example (`Inter`) does not apply; VerdictIn60 keeps `Helvetica`.
- **Small, consistent radii and borders over heavy shadows.** Cards are subtle bordered
  panels, not deep-shadowed boxes. Tkinter has no native shadow/blur, so this principle
  maps to `highlightthickness`/`highlightbackground` borders, which is already how
  `make_card()` works.
- **Micro-interactions signal state, not decoration.** Hover lift on cards, a pulsing
  dot for "in progress," a progress bar filling in — small motion cues that confirm
  something is scanning/loading/verifying. These map to Tkinter's `.after()`-driven
  animation, already used in `make_loading_state()`.

## Layout Patterns

Base44's shell: a collapsible left sidebar (nav + logo), a sticky top bar (search,
status pill, model selector, notifications, settings), and a scrollable content area
with a `max-width` centered container and consistent page padding.

Mapping to VerdictIn60's existing shell:

| Base44 pattern | VerdictIn60 equivalent | Notes |
|---|---|---|
| Collapsible left `Sidebar` with icon+label nav rows, active-item accent bar | Left nav built from `make_sidebar_button()` / `set_sidebar_active()` in `components.py` | Already implemented; collapse-to-icon-only is a plausible future enhancement, not a requirement |
| Sticky `TopBar` with global search, AI status pill, model selector, notifications | `make_top_bar()` per-tab header | VerdictIn60 has no global search or notifications; do not add these unless separately requested — they imply new functionality, not just UI |
| Centered `max-w-7xl` content column with `p-6` page padding | Tab content frames packed with a consistent outer `padx`/`pady` (e.g. `PAD = 36` in several tabs) | Keep a single consistent padding constant per tab; do not need a literal max-width since desktop windows are fixed/resizable, not fluid web layout |
| Route-based pages (`react-router-dom`) | Tkinter tab switching (`ttk.Notebook` / segmented tabs) | No router needed or wanted; "screens" in this doc mean "tabs/views," not URLs |

## Component Patterns

These are Base44 UI *patterns*, described abstractly (not the underlying Radix/Tailwind
implementation), alongside the closest existing VerdictIn60 building block:

- **Card** — bordered surface with padding, subtle hover brighten.
  → `make_card()` / `card_body()` already implement this.
- **Stat card** — icon chip, big bold value, muted label, optional up/down delta.
  → `make_metric_card()` covers value+label; no VerdictIn60 equivalent for the
  up/down delta arrow yet. If ever added, treat delta color as semantic (green/red
  from `SUCCESS`/`ERROR`), not `ACCENT`.
- **Status chip/pill** — small rounded label with a colored dot, some variants pulsing
  (scanning/verifying/generating) and some static (completed/failed/verified).
  → `make_badge()` covers the static case via `STATUS_STYLES`; `make_loading_state()`
  covers a pulsing dot + message, but as a row, not an inline pill. A pulsing *badge*
  variant (small dot inside a badge, animated via `.after()`) would need a small new
  helper if this pattern is wanted on a specific screen later.
- **Empty state** — centered icon in a soft tinted circle, short title, muted
  description, optional action button.
  → `make_empty_state()` currently renders text only; it lacks the icon-in-circle
  treatment and title/description split. Worth aligning later, not urgent.
- **Error banner** — tinted panel, bold heading with a warning glyph, muted message,
  optional retry action.
  → `make_error_banner()` already matches this pattern closely.
- **Segmented tab bar** (e.g. Settings' General/Appearance/AI/Models/...) — pill-style
  horizontal tabs with an active tinted-background pill.
  → `make_segmented_tabs()` already implements this and is used by `settings_tab.py`.
- **Source/verification list row** — kind badge + title + URL/confidence, in a bordered
  list panel.
  → `make_source_list()` and `make_confidence_badge()` already implement this.
- **Progress bar** — thin filled bar, color keyed to a confidence/percentage threshold
  (e.g. green ≥90%, amber ≥60%, red below).
  → No direct existing helper; would be a small new component (a `tk.Frame` with a
  width-proportional inner fill) if a screen needs it. Keep the same threshold logic
  as guidance if it's ever built.
- **Toolbar row above an editor** (character count, hashtag count, regenerate/copy
  actions) — compact row of small ghost buttons and inline counters above a large
  text area.
  → Partially present conceptually in caption-related screens; no shared helper yet.
- **Modal/dialog shell** — centered fixed-size panel, title + close button, divider,
  body content.
  → `make_toplevel_shell()` already implements this via `tk.Toplevel`.

Patterns that are **web-only and not applicable**: sidebar/nav via URL routing, a
command palette (`⌘K`), toasts stacked in a fixed viewport corner, hover-card/dropdown
menus built on Radix primitives, and anything driven by `framer-motion` spring physics.
Tkinter's `.after()`-based tweening is the substitute for simple, purposeful motion
(pulses, fades via incremental color steps) — not a general animation library.

## Screen-By-Screen Guidance

Mapping Base44's example screens to VerdictIn60's actual tabs. Screen names below are
preserved from the Base44 concept for traceability; VerdictIn60's real tab names are in
the right column.

| Base44 screen | Purpose in the concept | Closest VerdictIn60 tab | Guidance |
|---|---|---|---|
| Dashboard | Stat tiles (cases found, verified, captions generated, etc.) + recent activity feed | No direct 1:1 tab today | If a dashboard/overview tab is ever added, reuse `make_metric_card()` for tiles and a `make_card()` list (like `make_source_list()`'s row style) for an activity feed — do not introduce it speculatively |
| AI Case Hunter | Scan action, filters, a grid of case cards with viral/confidence scores and quick actions (Sources/Verify/Caption/Save) | Closest in spirit to case discovery/import flows across `url_import_tab.py` and `case_library.py` | Card-grid-with-quick-actions is a reasonable future direction for a "discover cases" surface, but VerdictIn60 does not currently do automated trending-case discovery — do not imply that functionality exists |
| URL Import | URL field + import button, step-by-step loading state, import history list | `url_import_tab.py` | Already the real equivalent; keep its existing loading/progress treatment (see Animation section) rather than replacing it wholesale |
| Caption Generator | Two-pane: caption editor with counters/toolbar on the left, tabbed verification/sources/AI-summary panel on the right | Caption review/edit surfaces reachable from `single_export_tab.py` / `batch_tab.py` and caption data in `verdictin60_captions.py` | The two-pane editor+verification-tabs layout is a good long-term shape for a caption review screen; the specific tab set (Verification/Sources/AI Summary) maps to VerdictIn60's existing source/confidence concepts in `verdictin60_core/research.py` |
| Verification | Summary tiles (verified/needs review/not verified counts) + filterable table of claims with confidence bars | Verification concepts live in `verdictin60_core/research.py`; surfaced today via `make_confidence_badge()`/`make_source_list()` inline in dialogs rather than a dedicated tab | A dedicated verification tab, if built, should reuse `make_metric_card()` for the summary tiles and the progress-bar pattern above for per-claim confidence |
| Saved Cases | Grid/list toggle, search, favoriting, per-case status chip | `library_tab.py` (`case_library.LibraryTab`) | This is the real equivalent; grid/list toggle and favoriting are enhancement ideas, not requirements |
| Export | Export-format cards (DOCX/PDF/Clipboard/Buffer-ready) + recent exports list | Export/publish flow in `verdictin60_core/export.py`, `verdictin60_core/publishing.py`, `batch_tab.py` | VerdictIn60's real export targets are ffmpeg-rendered reels, Internet Archive, and Buffer — not DOCX/PDF. Only the *card-grid-of-options* + *recent-activity-list* layout idea transfers; the specific export types must stay VerdictIn60's own |
| Settings | Segmented tabs: General/Appearance/AI/Models/Verification/Exports/Advanced, each a list of label+control rows | `settings_tab.py` | Already closely matches this shape (see `SETTINGS_TABS`); keep using `make_segmented_tabs()` and a consistent label+description+control row for any new setting |

Screens that are **not applicable**: Login/Register/Forgot-Password/Reset-Password
(Base44's hosted multi-user auth), since VerdictIn60 is a single-user local desktop
app with no login flow.

## Animation / Loading / Error-State Guidance

- **Loading/in-progress:** a small pulsing indicator (dot or spinner-style ring) paired
  with a short status label ("Scanning…", "Importing…", "Verifying…"). VerdictIn60's
  `make_loading_state()` already implements the pulsing-dot + message version via
  `.after()`; prefer extending that helper over hand-rolling a new animation per tab.
- **Multi-step progress:** when an operation has discrete steps (e.g. "Fetching
  metadata" → "Extracting thumbnail" → "Identifying case"), show them as a short
  vertical list where completed steps get a check and the current step gets a spinner.
  This is a reasonable pattern for `url_import_tab.py`'s import flow if it's ever
  broken into visible steps; keep it honest — only show steps the app actually
  performs, in the order it actually performs them.
- **Success/completion:** swap the in-progress indicator for a static checkmark badge
  in `SUCCESS`/`SUCCESS_BG`, not a new color.
- **Error state:** a bordered banner with a warning glyph, bold short title, muted
  explanation, and an optional retry action — this is exactly `make_error_banner()`.
  Keep error copy plain-language per `AI_RULES.md` ("Handle API errors with plain
  user-facing messages plus enough local detail for debugging").
- **Empty state:** icon + short title + one muted sentence of guidance + optional
  primary action, centered in the available space. Only show an empty state once a
  fetch/scan genuinely returned nothing — never as a placeholder for unbuilt features.
- **Motion budget:** keep animation purposeful and cheap. A pulsing dot, a fading
  status swap, or a filling progress bar are appropriate; anything resembling
  spring-physics page transitions or hover-lift on every element is web-dashboard
  flourish that doesn't fit a desktop utility app and risks janking the Tkinter main
  thread if not scheduled carefully.

## Tkinter Adaptation Notes

Concept-to-concept translation, so React/Tailwind-specific language in the source
material doesn't leak into VerdictIn60 work:

| Base44 (React/Tailwind) concept | Tkinter translation |
|---|---|
| Tailwind utility classes / `class-variance-authority` variants | Keyword-arg factory functions in `components.py`, driven by named tokens from `theme.py` |
| CSS custom properties (`--background`, `--primary`, etc.) in `index.css` | Module-level color constants in `theme.py` |
| `framer-motion` `animate`/`transition`/`AnimatePresence` | `widget.after(ms, callback)` loops (see `make_loading_state`'s `_tick`) |
| Radix UI primitives (Dialog, Select, Tabs, Tooltip, etc.) | Native `tk`/`ttk` widgets, or a small `components.py` helper when `ttk` doesn't fit the visual style |
| React component composition / props | Plain Python functions taking `parent` plus keyword args, returning the created widget (VerdictIn60's existing convention) |
| CSS `hover:` / `focus:` pseudo-classes | Explicit `<Enter>`/`<Leave>`/`<FocusIn>`/`<FocusOut>` bindings (see `_bind_hover` in `widgets.py`) |
| `react-router-dom` routes/pages | Tabs within the single Tkinter window; no URLs, no route guards |
| Toast notifications (`sonner`) | Not currently part of VerdictIn60; if ever needed, a transient `Toplevel` or an in-window banner, not a new dependency |
| Base44 SDK / hosted auth / multi-tenant `User` entity | Not applicable — VerdictIn60 has no backend, no login, and no multi-user concept |

## Migration Rules

These are hard constraints for any future work that draws on this document:

1. Do not introduce React, a web framework, a browser runtime, or Node-based UI
   tooling into VerdictIn60. The UI stays Python/Tkinter.
2. Do not add authentication, hosted backend calls, or a router. VerdictIn60 is a
   local single-user desktop app.
3. Do not adopt Base44's cyan/blue color palette or `Inter`/`JetBrains Mono` fonts.
   VerdictIn60's palette and fonts are defined in `verdictin60_ui/theme.py` and stay
   there; only the *structural* ideas (surface hierarchy, spacing scale, accent
   discipline) transfer.
4. Do not invent new functionality (global search, notifications, model picker,
   trending-case discovery, DOCX/PDF export) just because Base44's mock UI shows it.
   Only build UI for capabilities VerdictIn60 actually has or that are separately
   requested.
5. Prefer extending `verdictin60_ui/components.py` helpers over one-off styling in a
   single tab, so new UI stays consistent with the existing design system.
6. Any actual visual change to a real screen must be scoped, incremental, and
   explicitly requested — this document is background reference, not a work order.
7. Follow `docs/AI_RULES.md` UI Rules at all times: match the current dark visual
   style, keep long-running work off the Tkinter main thread, and marshal background
   thread UI updates through Tkinter-safe callbacks.

## Validation Checklist

Before treating any UI change as informed by this reference, confirm:

- [ ] The change uses tokens from `verdictin60_ui/theme.py`, not new hardcoded colors
      or fonts.
- [ ] The change reuses an existing `verdictin60_ui/components.py` helper where one
      fits, or adds a new helper there rather than duplicating styling inline.
- [ ] No new functionality was implied by the Base44 mock that VerdictIn60 doesn't
      actually have (auth, routing, hosted API calls, features not in
      `docs/ARCHITECTURE.md`).
- [ ] The app is still a Python/Tkinter desktop app — no web/React tooling was added.
- [ ] Status colors (`SUCCESS`/`WARNING`/`ERROR`) are used only for semantic state,
      never as a substitute for the crimson `ACCENT`.
- [ ] Any animation is implemented via `.after()` scheduling and does not block the
      Tkinter main thread.
- [ ] Error and empty states use plain-language copy consistent with
      `docs/AI_RULES.md`.
- [ ] The change was explicitly requested/scoped — this document was used as
      background reference, not as an implicit instruction to restyle a screen.
