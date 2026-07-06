# VerdictIn60 Architecture

VerdictIn60 is a Python desktop application centered around `app.py`, with `case_library.py` providing the local case database used by the Batch tab. The app is intentionally scoped to three tabs — Batch, Recovery, and Settings — and uses local files for settings, generated media, logs, cache, and SQLite data.

## High-Level Flow

```text
Local file / pasted or imported URL list / DOCX queue (Batch tab)
        |
        v
Tkinter app in app.py
        |
        +--> URL title/caption detection through verdictin60_core/batch_intake.py
        |       (yt-dlp metadata probe, page-title fetch, AI caption draft,
        |        template fallback — runs in the background per URL)
        +--> source download through yt-dlp (for queued URL rows, at run time)
        +--> video processing through ffmpeg and assets/
        +--> upload through Internet Archive
        +--> scheduling through Buffer
        +--> case tracking through case_library.py and case_library.db
```

## Main Modules

### app.py

Responsibilities:

- App startup and Tkinter UI: Batch tab, Recovery tab, and the Settings dialog.
- Settings loading and saving through `settings.json`.
- DOCX queue parsing from `VerdictIn60_Import_With_Captions.docx`.
- Batch caption formatting/reformatting.
- ffmpeg export pipeline.
- Internet Archive upload.
- Buffer scheduling.
- Recovery assistant and health checks.

### case_library.py

Responsibilities:

- Local SQLite database management through `case_library.db`.
- Case upsert, status update, caption edit, delete, and timeline events.
- Buffer scheduled-post sync.
- Thumbnail generation with Pillow.

### verdictin60_captions.py

Responsibilities:

- Stores predefined caption content keyed by case name.
- Acts as a local caption library/reference.

## Data And Storage

Local storage paths are rooted beside `app.py`:

- `settings.json`: local credentials and preferences. Ignored by Git.
- `case_library.db`: SQLite case database. Ignored by Git.
- `finished-reels/`: generated final videos. Ignored by Git.
- `_docx_downloads/`: downloaded source videos. Ignored by Git.
- `library_thumbs/`: generated thumbnails. Ignored by Git.
- `export-log.txt` and other `*.log`: local logs. Ignored by Git.

## Video Pipeline

The app uses:

- `yt-dlp` for downloading source media.
- `ffmpeg` and `ffprobe` for media probing, normalization, rendering, concatenation, and final output.
- `assets/logo.png`, `assets/voiceover.mp3`, and `assets/cta-endcard.mp4` as required media assets.

Long-running video work should remain off the Tkinter main thread.

## AI/Provider Settings

Settings exposes AI speed mode and provider configuration (`verdictin60_core/ai.py`), and Recovery's health check verifies that the configured Ollama models are installed. Batch's "Paste / Import URLs" flow (`verdictin60_core/batch_intake.py`) is the first caller of the AI caption pipeline: it drafts a short caption body per pasted URL through `ai_generate`/`ai_task_ready`, which already routes through the safety/cost guard (`verdictin60_core/provider_guard.py`), and falls back to a local template (marked "needs review") whenever AI is unavailable, disabled, or fails. The draft body still passes through the existing `reformat_caption` step in `app.py` at run time to get its hashtags/CTA, same as a manually-pasted caption.

## Upload And Scheduling

Internet Archive is used as public video hosting for Buffer. The upload flow returns a public video URL, then the app waits or retries until the URL is available. Buffer scheduling uses Buffer API credentials and the configured Instagram channel ID.

## Threading Model

Tkinter must remain responsive. Background work is used for:

- yt-dlp downloads.
- ffmpeg processing.
- uploads and scheduling.
- Buffer sync.
- thumbnail generation.

UI updates from background work should be marshalled back through Tkinter-safe callbacks such as `after`.

## Risk Areas

- Credential leaks through logs, settings, examples, or commits.
- UI freezes from blocking network or ffmpeg calls on the main thread.
- Buffer API changes or GraphQL response shape changes.
- Internet Archive upload propagation delays.
- yt-dlp changes or browser-cookie access issues.
- ffmpeg command regressions that break finished reel output.

## Safe Change Strategy

Prefer small changes that preserve the existing flow. For risky areas, add a dry-run path, clear logging with redacted secrets, and a user-facing error message that explains what to check next.
