# VerdictIn60

VerdictIn60 is a local macOS desktop app for producing and scheduling short true-crime reels. It's built in Python with Tkinter for the UI, and helps import source video, prepare finished vertical reels, generate or review captions, upload finished media, and schedule posts while keeping a local case library.

## What It Does

1. Import a source video manually, from a URL, or from a DOCX queue.
2. Identify or enter the true-crime case title.
3. Generate, review, or paste an Instagram-ready caption.
4. Produce a finished reel with the configured assets.
5. Upload the finished media to Internet Archive.
6. Schedule the post through Buffer.
7. Track the case in a local SQLite-backed library.

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

- `app.py` — main Tkinter application: settings dialog, URL import, DOCX queue import, caption generation/review, ffmpeg export, Internet Archive upload, Buffer scheduling, and recovery assistant.
- `case_library.py` — SQLite case library, Buffer sync, case cards, detail dialog, status updates, captions, timelines, and thumbnail generation.
- `verdictin60_captions.py` — built-in caption library and caption text content.
- `verdictin60_core/` — core helpers for AI calls, captions, export, imports, paths, publishing, recovery, research, scheduling, settings, and utilities.
- `verdictin60_ui/` — Tkinter UI modules: tabs, shared widgets, and the app's design system/theme.
- `assets/` — required media assets (logo, voiceover, CTA end card).
- `requirements.txt` — Python package requirements.
- `docs/` — project documentation for maintainers and AI assistants (`AI_RULES.md`, `ARCHITECTURE.md`, `PROJECT_CONTEXT.md`, `ROADMAP.md`).

## Current UI Refactor Status

The Tkinter UI is being refactored around a single design system (`verdictin60_ui/theme.py`): a black/crimson brand palette with semantic status colors, so every screen pulls shared colors, fonts, and spacing instead of hardcoding values. This refactor is inspired by a separate Base44 UI reference, but the app itself remains a Python/Tkinter desktop app, not a React app.

`docs/UI_RECONSTRUCTION_REFERENCE.md` will be added later as the Base44-inspired UI design reference.

## Local-Only Files

These files and folders are intentionally not committed (see `.gitignore`): `settings.json`, `.env`/`.env.*`, `case_library.db`, `finished-reels/`, `_docx_downloads/`, `library_thumbs/`, `ms-playwright/`, `vendor/`, and local logs.

See `docs/PROJECT_CONTEXT.md` and `docs/ARCHITECTURE.md` for more detail.
