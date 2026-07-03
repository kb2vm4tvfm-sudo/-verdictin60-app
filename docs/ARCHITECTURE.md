# VerdictIn60 Architecture

VerdictIn60 is a Python desktop application centered around `app.py`, with `case_library.py` providing the local case database and library UI. The app uses local files for settings, generated media, logs, cache, and SQLite data.

## High-Level Flow

```text
User input / DOCX / URL
        |
        v
Tkinter app in app.py
        |
        +--> source download and metadata through yt-dlp
        +--> caption generation and verification through Ollama and web sources
        +--> video processing through ffmpeg and assets/
        +--> upload through Internet Archive
        +--> scheduling through Buffer
        +--> case tracking through case_library.py and case_library.db
```

## Main Modules

### app.py

Responsibilities:

- App startup and Tkinter UI.
- Settings loading and saving through `settings.json`.
- DOCX queue parsing from `VerdictIn60_Import_With_Captions.docx`.
- URL import with yt-dlp and browser-cookie fallbacks.
- Source research and verification helpers.
- Ollama model selection and local AI calls.
- Caption formatting, fallback captions, and caption review.
- ffmpeg export pipeline.
- Internet Archive upload.
- Buffer scheduling.
- Instagram/Meta connection helpers and metrics lookup.
- Recovery assistant and health checks.

### case_library.py

Responsibilities:

- Local SQLite database management through `case_library.db`.
- Case upsert, status update, caption edit, delete, and timeline events.
- Buffer scheduled-post sync.
- Thumbnail generation with Pillow.
- Library grid UI and case detail dialog.

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
- `source-cache.json`: source research cache. Ignored by Git.
- `export-log.txt` and other `*.log`: local logs. Ignored by Git.

## Video Pipeline

The app uses:

- `yt-dlp` for downloading source media.
- `ffmpeg` and `ffprobe` for media probing, normalization, rendering, concatenation, and final output.
- `assets/logo.png`, `assets/voiceover.mp3`, and `assets/cta-endcard.mp4` as required media assets.

Long-running video work should remain off the Tkinter main thread.

## Caption And AI Pipeline

The app can use Ollama models in speed modes:

- Fast.
- Balanced.
- Best Accuracy.

Caption generation should remain grounded in available sources. When source confidence is low or AI fails, the app falls back to safer caption behavior instead of fabricating details.

## Upload And Scheduling

Internet Archive is used as public video hosting for Buffer. The upload flow returns a public video URL, then the app waits or retries until the URL is available. Buffer scheduling uses Buffer API credentials and the configured Instagram channel ID.

## Threading Model

Tkinter must remain responsive. Background work is used for:

- yt-dlp downloads.
- ffmpeg processing.
- Ollama calls.
- source fetching.
- uploads and scheduling.
- Buffer sync.
- thumbnail generation.

UI updates from background work should be marshalled back through Tkinter-safe callbacks such as `after`.

## Risk Areas

- Credential leaks through logs, settings, examples, or commits.
- UI freezes from blocking network, ffmpeg, or AI calls on the main thread.
- Buffer API changes or GraphQL response shape changes.
- Internet Archive upload propagation delays.
- yt-dlp changes or browser-cookie access issues.
- ffmpeg command regressions that break finished reel output.
- Caption hallucinations or unverified true-crime claims.

## Safe Change Strategy

Prefer small changes that preserve the existing flow. For risky areas, add a dry-run path, clear logging with redacted secrets, and a user-facing error message that explains what to check next.
