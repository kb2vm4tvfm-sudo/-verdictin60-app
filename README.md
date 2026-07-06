# VerdictIn60

VerdictIn60 is a local macOS desktop app for producing and scheduling short true-crime reels. It's built in Python with Tkinter for the UI, and helps batch-process source videos (from files, URLs, or a DOCX queue), produce finished vertical reels, upload finished media, and schedule posts through Buffer. The app is focused on three tabs: **Batch**, **Recovery**, and **Settings**.

## What It Does

1. Queue source videos in Batch — from local files, pasted URLs, or a DOCX queue.
2. Produce a finished reel with the configured assets for each queued video.
3. Upload the finished media to Internet Archive.
4. Schedule the post through Buffer.
5. Track each case in a local SQLite-backed library.
6. Use Recovery to run a local health check and repair common setup problems.

## Install & Run

Requirements:

- Python 3
- ffmpeg and ffprobe
- yt-dlp
- Ollama, for local AI calls

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Optional: enable browser-based source reading:

```bash
./install_browser_reader.command
```

Optional: install Ollama and pull the local model:

```bash
./install_ollama.sh
```

Launch the app:

```bash
./launch.command
```

or directly:

```bash
python3 app.py
```

## Main Files & Folders

- `app.py` — main Tkinter application: Batch tab, Recovery tab, settings dialog, ffmpeg export, Internet Archive upload, and Buffer scheduling.
- `case_library.py` — SQLite case library: Buffer sync, status updates, captions, timelines, and thumbnail generation.
- `verdictin60_captions.py` — built-in caption library and caption text content.
- `verdictin60_core/` — core helpers for AI calls, captions, export, imports, paths, publishing, recovery, scheduling, settings, and utilities.
- `verdictin60_ui/` — Tkinter UI modules for the Batch/Recovery/Settings tabs, shared widgets, and the app's design system/theme.
- `assets/` — required media assets (logo, voiceover, CTA end card).
- `requirements.txt` — Python package requirements.
- `docs/` — project documentation for maintainers and AI assistants (`AI_RULES.md`, `ARCHITECTURE.md`, `PROJECT_CONTEXT.md`, `ROADMAP.md`).

## Current UI Refactor Status

The Tkinter UI is being refactored around a single design system (`verdictin60_ui/theme.py`): a black/crimson brand palette with semantic status colors, so every screen pulls shared colors, fonts, and spacing instead of hardcoding values. This refactor is inspired by a separate Base44 UI reference, but the app itself remains a Python/Tkinter desktop app, not a React app.

The Base44-inspired UI reconstruction reference is documented in:

- `docs/UI_RECONSTRUCTION_REFERENCE.md`

## Local-Only Files

These files and folders are intentionally not committed (see `.gitignore`): `settings.json`, `.env`/`.env.*`, `case_library.db`, `finished-reels/`, `_docx_downloads/`, `library_thumbs/`, `ms-playwright/`, `vendor/`, and local logs.

See `docs/PROJECT_CONTEXT.md` and `docs/ARCHITECTURE.md` for more detail.
