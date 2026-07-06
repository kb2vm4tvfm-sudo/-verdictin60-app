# VerdictIn60 Roadmap

This roadmap is a living guide. Keep changes practical and focused on making the app safer, more reliable, and easier to operate.

## Phase 1: Repository Hygiene

- Add project documentation for AI assistants and future maintainers.
- Add a human-friendly `README.md` with install, launch, and update instructions.
- Add a safe `settings.example.json` with placeholder values only.
- Confirm `.gitignore` covers all generated media, local credentials, logs, caches, and packaged app output.

## Phase 2: Safer Configuration

- Move credential handling toward environment variables or a local-only settings file.
- Add startup checks that clearly show which services are configured without revealing values.
- Redact secrets from all console output and logs.
- Add a one-click or guided way to reset/replace saved credentials.

## Phase 3: Reliability

- Add focused tests for pure helper functions such as filename cleaning, caption formatting, DOCX queue parsing, source classification, and scheduling date calculations.
- Add dry-run modes for upload and Buffer scheduling.
- Improve error recovery for yt-dlp, ffmpeg, Ollama, Internet Archive, and Buffer failures.
- Make long-running flows resumable where practical.

## Phase 4: Caption And Verification Quality (historical — superseded by Phase 9)

This phase applied to the URL Import caption-verification review dialog, which was removed in Phase 9. Kept for history only.

## Phase 5: Case Library Improvements (historical — superseded by Phase 9)

This phase applied to the Library/Saved Cases grid UI, which was removed in Phase 9. `case_library.py`'s underlying `CaseLibrary` data layer (used by Batch) is unaffected.

## Phase 6: Packaging And Distribution

- Document how the `.app` bundle is built.
- Keep packaged app output out of GitHub.
- Add a repeatable build checklist.
- Add a release checklist for local testing, credentials, app launch, export, and scheduling.

## Phase 7: Research Hub (historical — removed in Phase 9)

Built a "Research Hub" tab (issue #52) with AI case identification, budgeted source research, and Wayback Machine archive recovery. Removed in Phase 9 along with `verdictin60_core/research.py`/`research_hub.py`; no longer part of the app.

## Phase 9: Simplification To Batch / Recovery / Settings

- Removed the Library/Saved Cases, URL Import, Research Hub, and Single Export tabs from the main navigation (issue #70).
- Kept Batch (including Buffer scheduling/publishing), Recovery, and Settings (AI/provider settings, Buffer settings, safety/cost guard) fully working.
- Removed the now-dead UI modules (`url_import_tab.py`, `library_tab.py`, `research_tab.py`, `single_export_tab.py`) and the `LibraryTab`/`CaseDetailDialog` UI classes from `case_library.py`; kept the shared `CaseLibrary` data layer, `verdictin60_core/export.py`, and `verdictin60_core/imports.py` since Batch still depends on them.
- Removed `verdictin60_core/research.py` and `research_hub.py`, which had no callers left after Research Hub and URL Import were removed.

## Nice-To-Have Ideas

- A local dashboard showing service health.
- Import validation for DOCX queue rows.
- A safer local secret store using macOS Keychain.
- Optional command-line tools for batch import and dry-run validation.
