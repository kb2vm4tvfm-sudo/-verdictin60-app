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

## Local, Development-Only Footprint

If the Ruflo wizard generates local config or state files in this repo
checkout (for example, a `.ruflo/` directory), treat them as local developer
state:

- Do not commit generated Ruflo state/config to this repository.
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
