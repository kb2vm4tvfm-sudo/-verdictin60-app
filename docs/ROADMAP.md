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

## Phase 4: Caption And Verification Quality

- Improve source ranking and confidence scoring.
- Make the review dialog clearer about verified facts versus unverified video-caption context.
- Add a lightweight citation preview before caption approval.
- Preserve creator credit and source disclosure behavior.

## Phase 5: Case Library Improvements

- Add backup/export for `case_library.db`.
- Add filters for platform, date range, status, and missing thumbnail.
- Improve thumbnail regeneration and manual thumbnail selection.
- Add richer timeline events for failed uploads, retries, and manual edits.

## Phase 6: Packaging And Distribution

- Document how the `.app` bundle is built.
- Keep packaged app output out of GitHub.
- Add a repeatable build checklist.
- Add a release checklist for local testing, credentials, app launch, export, and scheduling.

## Nice-To-Have Ideas

- A local dashboard showing service health.
- Import validation for DOCX queue rows.
- A safer local secret store using macOS Keychain.
- Optional command-line tools for batch import and dry-run validation.

## Phase 9: Research Hub Follow-Ups

The Research Hub tab (search panel, AI case finder, source gathering, Wayback
archive recovery, case summary/sources display, and Save/Caption/Copy/Export
actions) shipped as a first version on top of `verdictin60_core/research_hub.py`
and `verdictin60_ui/research_tab.py`. Deferred for a follow-up change:

- A built-in AI chat assistant that can answer follow-up questions about the
  current case ("find more official sources", "summarize the timeline") —
  the first version only supports a single Investigate pass plus a manual
  "Continue Research" re-run.
- PDF export (Markdown export is included; PDF needs a new dependency).
- Drag-and-drop of links/files into the search panel (needs a new Tkinter
  drag-and-drop dependency; pasting multiple links/lines is supported today).
- Automated lookups against Archive.today, Memento Time Travel, and
  CachedView. These don't have stable, scrape-safe APIs, so the first version
  only automates Wayback Machine recovery and hands the user direct manual
  lookup links for the other three services instead of guessing results.
- A dedicated "Generate Verification Report" action distinct from the
  Markdown export.
