# Optional: Ruflo Dev Workflow Tooling

This document explains how to optionally use [Ruflo](https://github.com/ruvnet/ruflo)
when developing VerdictIn60. Ruflo is **not** part of the VerdictIn60 desktop app.

## What Ruflo Is (And Isn't)

Ruflo is a standalone, third-party agent-coordination / developer-workflow tool
aimed at helping AI coding agents (Claude Code, Codex, and similar tools)
organize multi-step work in a repository. It is not related to VerdictIn60's
video, caption, upload, or scheduling features.

- Ruflo is **development tooling only**, used at the discretion of a
  contributor working on this repo. It has nothing to do with the end-user
  desktop app that ships to VerdictIn60 users.
- VerdictIn60 does **not** depend on Ruflo to build, launch, or run. Nothing
  in `app.py`, `verdictin60_core/`, or `verdictin60_ui/` imports or calls it.
- Installing Ruflo is entirely optional. If you never install it, VerdictIn60
  behaves exactly as before.

## Why It's Not A Project Dependency

VerdictIn60 is a Python/Tkinter desktop app (see `requirements.txt` and
`docs/PROJECT_CONTEXT.md`). Ruflo is a separate Node.js-based CLI tool used
outside of the app's own process, purely to help a developer or AI assistant
plan and coordinate changes to this repo. Because of that:

- Ruflo is **not** listed in `requirements.txt` and should not be added there.
- Ruflo is **not** invoked from app startup, `launch.command`, or any
  in-app code path.
- No API keys or paid services are required to use it in the way described
  below.

## The Main Benefit: Less Rereading, Lower Token Usage

Without any persistent project memory, an AI assistant (Claude Code, Codex,
etc.) working on this repo tends to re-read most of `docs/`, skim `app.py`,
`case_library.py`, and the core/UI packages, and re-derive the same
architecture facts at the start of nearly every session or task. That's slow
and burns a lot of tokens before any real work starts.

Ruflo's optional value here is as a **persistent, local project
memory/context layer**:

- It can hold a standing summary of the repo (current scope, architecture,
  safety rules, common commands) so an agent can consult a short memory file
  instead of re-scanning the whole tree and every doc.
- It reduces repeated context loading across sessions — the agent reads a
  compact memory once instead of rediscovering the same facts every time.
- Lower token usage follows directly from less rereading: a short "what this
  repo is and what matters" memory is far cheaper than re-ingesting
  `ARCHITECTURE.md`, `PROJECT_CONTEXT.md`, `AI_RULES.md`, and the source tree
  each time.
- Faster issue/PR turnaround: an agent that already "remembers" the current
  product shape, removed features, and safety rules can get to the actual
  change faster instead of spending the first pass re-establishing context.

None of this changes what the app does — it only changes how efficiently an
AI assistant can *start* working on it.

## Optional Setup

If you'd like to try Ruflo for your own agent/dev workflow while contributing
to VerdictIn60, you can install it on demand with `npx` — no permanent
install or project dependency is required:

```bash
# Optional — only run this if you want Ruflo's dev workflow tooling.
npx ruflo@latest init wizard
```

Follow the interactive wizard's prompts. Refer to the
[upstream Ruflo repository](https://github.com/ruvnet/ruflo) for full
documentation, configuration options, and updates, since this file only
covers how it relates to VerdictIn60.

If the wizard offers to create local memory/context files (for example, a
`.ruflo/` directory), that's the piece that delivers the token-savings
benefit described above — see the next two sections for what's safe to put
in it.

## What To Store In Ruflo Memory/Context

Keep memory content to durable, non-secret facts about the repo — things
that are expensive to re-derive but cheap to state once:

- **Current product shape**: the app is scoped to three tabs — Batch,
  Recovery, and Settings. Batch is the main workflow (queue → build reel →
  upload → schedule → track in the case library).
- **Removed features** (so an agent doesn't try to "restore" or reference
  them as if current): the Library/Saved Cases tab, the URL Import tab, the
  Research Hub tab, and the Single Export tab were all removed in Phase 9
  (see `docs/ROADMAP.md`). Their underlying data layer (`CaseLibrary` in
  `case_library.py`) and shared helpers (`verdictin60_core/export.py`,
  `verdictin60_core/imports.py`) remain because Batch still depends on them.
- **Key safety rules** (see `docs/AI_RULES.md` for the authoritative
  versions):
  - No paid/quota-limited AI provider calls should be retried or continued
    after a quota, billing, rate-limit, or auth-shaped failure — this goes
    through `verdictin60_core/provider_guard.py` (`is_provider_disabled`,
    `report_failure`).
  - Buffer scheduling behavior must be preserved; it's a core step in the
    Batch workflow, not an optional add-on.
  - Batch is the main workflow and should stay the primary, fully working
    path through the app.
- **Repo architecture summary**: a short pointer-style summary is enough —
  `app.py` (Tkinter UI: Batch/Recovery/Settings, export, upload, scheduling),
  `case_library.py` (SQLite case data + Buffer sync), `verdictin60_captions.py`
  (caption content), `verdictin60_core/` (provider guard, AI, export, import
  helpers). Full detail always lives in `docs/ARCHITECTURE.md`; memory only
  needs enough to avoid re-reading it every time.
- **Common commands for local testing**, for example:
  ```bash
  python3 app.py
  pip install -r requirements.txt
  ```
- **Known local path notes**, if useful for your own machine (e.g. where you
  keep a local `settings.json` or a local Ollama install) — but see the next
  section: never the values themselves, only that such local files exist and
  are gitignored.

## What Not To Store

Never put the following into Ruflo memory/context files, prompts, or any
other file that might be read back by an agent or committed to the repo:

- API keys (Ollama/NVIDIA NIM or any other provider).
- Buffer tokens or Buffer API credentials.
- NVIDIA keys or any other cloud AI provider credentials.
- Personal credentials of any kind (passwords, session cookies, tokens).
- Private customer/case data (real case details, real uploaded media
  references, anything from a real user's `case_library.db` or
  `settings.json`).
- Large generated files (finished reels, downloaded source media,
  thumbnails, logs, databases) — these belong in the already-gitignored
  local folders (`finished-reels/`, `_docx_downloads/`, `library_thumbs/`,
  `case_library.db`, `*.log`), not in memory/context files.

If you're ever unsure whether something is safe to store, treat it like any
other content you wouldn't commit to git: leave it out. See
`docs/AI_RULES.md`'s "Protect Secrets" section for the same rule applied to
the codebase generally.

## Claude/Codex Starting Prompt Example

When starting a session with Ruflo (or any persistent project memory) set
up, point the agent at it first instead of having it scan the whole repo:

```text
Before reading through the repository, check Ruflo/project memory for
existing context on VerdictIn60 (current tabs, architecture, safety rules,
and removed features). Only read source files or docs directly relevant to
this task, and re-scan a doc in full only if the memory looks stale or is
missing something you need.
```

This is only useful if the memory is kept short and current — if it grows
stale, prefer re-reading `docs/PROJECT_CONTEXT.md` and
`docs/ARCHITECTURE.md` directly rather than trusting outdated memory.

## Local, Development-Only Footprint

If the Ruflo wizard generates local config or state files in this repo
checkout (for example, a `.ruflo/` directory), treat them as local developer
state:

- Do not commit generated Ruflo state/config to this repository unless it's
  a deliberately shared, secret-free template meant to be tracked.
- If you find yourself with Ruflo-generated files tracked by git, add the
  relevant path to `.gitignore` rather than checking it in.

## What This Does Not Change

Adding this document does not change:

- The Batch, Recovery, or Settings tabs.
- Buffer, Internet Archive, or AI provider (Ollama/NVIDIA NIM) behavior.
- Export, caption, or scheduling behavior.
- `requirements.txt` or how the app starts (`launch.command` / `python3 app.py`).

See `docs/AI_RULES.md` for the rules AI assistants should follow when editing
this codebase, and `docs/PROJECT_CONTEXT.md` for the app's overall purpose.
