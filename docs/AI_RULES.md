# AI Editing Rules

Read this file before editing VerdictIn60. These rules apply to Claude Code, Codex, ChatGPT, and any other AI assistant working on the project.

## Protect Secrets

- Never commit `settings.json`, `.env`, `.env.*`, API keys, tokens, passwords, session cookies, or credentials.
- Never print real secrets in logs, docs, examples, tests, screenshots, or terminal output.
- If a secret appears in output, tell the user to rotate it.
- Use placeholders in examples, such as `YOUR_BUFFER_API_KEY` or `YOUR_META_APP_SECRET`.

## Respect Local Data

- Do not delete or overwrite `case_library.db`, `finished-reels/`, `_docx_downloads/`, `library_thumbs/`, or user media unless the user explicitly asks.
- Treat generated videos, downloaded sources, local logs, and browser caches as user data.
- Keep `.gitignore` strict. If a new generated folder or local credential file appears, add it to `.gitignore`.

## Preserve The Workflow

The core workflow is:

1. Import or select source media.
2. Determine case title.
3. Build or review caption.
4. Export reel through ffmpeg.
5. Upload to Internet Archive.
6. Schedule through Buffer.
7. Save/update case library state.

Do not make changes that break this flow without an explicit migration plan.

## Be Careful With External APIs

- Buffer, Meta/Instagram, Internet Archive, Ollama, yt-dlp, Playwright, and ffmpeg all have fragile edge cases.
- Keep timeouts and background threads responsive so the Tkinter UI does not freeze.
- Prefer small, testable changes around upload, scheduling, caption generation, and source verification.
- Handle API errors with plain user-facing messages plus enough local detail for debugging.

## Cost / Quota Safety Guard (issue #61)

- Any call to a paid or quota-limited AI/cloud provider (NVIDIA NIM today; a future
  Claude/Anthropic, Codex/OpenAI, or other connector) must go through
  `verdictin60_core/provider_guard.py` before the network request:
  - Check `provider_guard.is_provider_disabled("<provider>")` first and skip the call
    (falling back to local/non-AI behavior) if it returns `True`.
  - On failure, call `provider_guard.report_failure("<provider>", status_code=...)` (or
    with a sanitized message) so quota/billing/rate-limit/auth/timeout-shaped failures
    disable the provider instead of being retried (a bare timeout gets a short cooldown,
    not the long quota/auth disable — see `TIMEOUT_COOLDOWN_SECONDS`).
  - Never pass an API key, token, cookie, or Authorization header into
    `report_failure` — only a status code or an already-sanitized message.
- Do not add retry loops around a paid/quota-limited provider call. One attempt, then
  fall back or surface a non-blocking warning — see `verdictin60_core/ai.py`'s
  `_nvidia_call` / `ai_generate` / `ai_identify` for the pattern to follow.
- Cloud providers must never be required for the app to start or for local-only mode
  to keep working.

## UI Rules

- Keep the app focused on the desktop workflow, not a marketing-style interface.
- Match the current dark visual style and existing controls.
- Do not add large rewrites of the Tkinter UI unless requested.
- Long-running work must run off the main UI thread.
- UI updates from background threads should be scheduled safely through Tkinter callbacks.

## Caption And Research Rules

- True-crime captions must avoid inventing facts.
- Distinguish verified facts from details found only in source video captions.
- Keep source and confidence language intact unless deliberately improving verification quality.
- Do not remove creator credit behavior unless the user requests it.

## Code Style Rules

- Follow the existing Python style and file organization.
- Prefer small focused edits over broad refactors.
- Avoid introducing new dependencies unless they clearly reduce risk or complexity.
- Use existing helpers before adding new ones.
- Keep comments useful and sparse.

## Before Committing

Run these checks:

```bash
git status
git diff --cached --name-only
git diff --cached --name-only | grep -E '(^|/)(\.env|settings\.json|case_library\.db)|token|secret|key|\.log$|ms-playwright|vendor|_docx_downloads|finished-reels|library_thumbs|VerdictIn60 Reel Editor\.app'
```

The final command should print nothing before committing.
