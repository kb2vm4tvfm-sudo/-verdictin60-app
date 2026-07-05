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

## Phase 7: Research Hub

- Built: a "Research Hub" tab (issue #52) — paste any combination of names, locations, dates, keywords, headlines, or platform URLs; AI case identification (title/aliases/confidence/reasoning/victims/suspects/timeline/outcome) that never invents facts and states plainly when confidence is too low, with a clue-based Low-confidence fallback if local AI identification times out; budgeted source research (`deadline_seconds`/`max_sources`) reusing the shared `research.py` pipeline; Wayback Machine archive recovery with manual lookup links for Archive.today/Memento/CachedView; results grouped into Official / Reporting (Accessible) / Reporting (Archived) / Blocked; Save to Case Library, Generate Caption, Copy All Sources, Copy Archive Links, Open All Sources, and Export Markdown actions.
- Deferred follow-ups:
  - A conversational AI research assistant (chat) that can answer follow-up questions grounded in the collected evidence — the current version supports one Investigate pass per set of clues.
  - PDF export of the research report (Markdown export is available today).
  - Drag-and-drop input for links (pasting multiple lines/links already works; drag-and-drop would need a new Tkinter dependency).

## Nice-To-Have Ideas

- A local dashboard showing service health.
- Import validation for DOCX queue rows.
- A safer local secret store using macOS Keychain.
- Optional command-line tools for batch import and dry-run validation.
