# VerdictIn60 Project Context

VerdictIn60 is a local macOS desktop app for producing and scheduling short true-crime reels. It is built primarily in Python with Tkinter for the UI. The app is scoped to three tabs — Batch, Recovery, and Settings — and helps batch-process video sources, prepare finished vertical reels, upload media, schedule posts, and keep a local case library.

## Core Purpose

The app supports a repeatable content workflow through the Batch tab:

1. Queue a source video from a local file, a pasted URL, or a DOCX queue.
2. Produce a finished reel with the configured assets.
3. Upload the finished media to Internet Archive.
4. Schedule the post through Buffer.
5. Track the case in a local SQLite-backed library.

The Recovery tab runs a local health check and repairs common setup problems; the Settings dialog manages AI/provider settings, Buffer settings, and the safety/cost guard.

## Important Source Files

- `app.py`: main Tkinter application — Batch tab, Recovery tab, settings dialog, DOCX queue import, ffmpeg export, Internet Archive upload, and Buffer scheduling.
- `case_library.py`: SQLite case library, Buffer sync, status updates, captions, timelines, and thumbnail generation.
- `verdictin60_captions.py`: built-in caption library and caption text content.
- `requirements.txt`: Python packages required by the project.
- `assets/`: required media assets such as logo, voiceover, and CTA end card.
- `.gitignore`: keeps local secrets, caches, generated media, logs, databases, browser downloads, and app bundles out of GitHub.

## Local-Only Files

These files or folders are intentionally local and should not be committed:

- `settings.json`: contains API keys, tokens, credentials, and local preferences.
- `.env` and `.env.*`: environment variables and secrets.
- `case_library.db`: local SQLite database.
- `finished-reels/`: generated output videos.
- `_docx_downloads/`: downloaded source media.
- `library_thumbs/`: generated thumbnails.
- `ms-playwright/`: local Playwright browser downloads.
- `vendor/`: local vendored runtime packages.
- `*.log`: local debug and export logs.
- `VerdictIn60 Reel Editor.app/`: packaged macOS app bundle.

## External Tools And Services

The app relies on these local tools and external services:

- Python 3.
- Tkinter for the desktop UI.
- ffmpeg and ffprobe for video processing.
- yt-dlp for URL/video downloads (queued in Batch).
- Ollama for local AI model calls (configured in Settings; checked by Recovery).
- Internet Archive S3-style upload API for public video hosting.
- Buffer GraphQL API for scheduling Instagram posts.

## Current GitHub Upload Scope

The initial GitHub upload includes the source code, assets, requirements, `.gitignore`, and the DOCX import template. It does not include local credentials, logs, local database files, downloaded media, generated finished reels, Playwright browser files, or the packaged app bundle.

## Security Note

Real tokens were found in `settings.json` during local scanning. That file is ignored and was not uploaded, but the credentials should still be rotated because they appeared in terminal output during the upload process.
