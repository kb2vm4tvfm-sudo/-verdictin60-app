"""Batch URL intake — turn a bare pasted/imported URL into a draft batch
queue item (issue #72), so the user doesn't have to hand-build a DOCX row
with URL / case title / caption for every source.

`build_batch_item_from_url` never raises: every failure (yt-dlp probe,
page-title fetch, AI generation) is caught and turned into a clearly marked
"needs review" field instead, so one bad URL can't stop the rest of a
paste/import batch. It reuses:

- verdictin60_core/imports.py's yt-dlp metadata probe / page-title / URL-slug
  fallback chain for title detection.
- verdictin60_core/ai.py's provider-aware ai_generate() (Ollama by default,
  optional NVIDIA NIM per the user's AI Provider setting) for a draft caption
  body, which already routes through provider_guard.py's cost/quota guard.
- A local template fallback (no AI call at all) whenever AI captioning is
  unavailable, disabled, or fails.

The returned caption is a bare draft body only (no hashtags/CTA) — the
existing reformat_caption() step in app.py's batch run already appends those
consistently for every non-DOCX row, so this module doesn't need to
duplicate that formatting.
"""
from verdictin60_core.ai import ai_generate, ai_task_ready
from verdictin60_core.imports import fetch_page_title, probe_url_metadata, title_from_url


def _detect_title(url: str, settings: dict) -> tuple[str, str, str, str]:
    """Return (title, source, description, probe_error). source is
    "detected" if any tier found a title, else "needs_review". description
    only ever comes from the yt-dlp metadata tier (page-title/URL-slug
    fallbacks don't have one)."""
    meta = probe_url_metadata(url, settings)
    title = meta.get("title", "")
    description = meta.get("description", "") if title else ""
    if not title:
        title = fetch_page_title(url)
    if not title:
        title = title_from_url(url)
    source = "detected" if title else "needs_review"
    return title, source, description, meta.get("error", "")


def _ai_caption_body(title: str, description: str) -> str:
    """Try a short AI caption draft; return "" if AI is unavailable, disabled,
    or the call fails for any reason, so the caller falls back to a template."""
    if not title or not ai_task_ready("caption"):
        return ""
    prompt = (
        "Write a short true-crime Instagram caption draft (3-5 sentences, no "
        "hashtags, no sign-off) for a case titled "
        f"\"{title}\".\nOnly use the details given below — do not invent facts. "
        "If details are sparse, keep the draft brief and generic.\n"
        f"Known details: {description[:800] or 'none provided'}"
    )
    try:
        return ai_generate(prompt, task="caption", num_predict=400).strip()
    except Exception:
        return ""


def _template_caption_body(title: str, description: str) -> str:
    """Deterministic, non-AI caption draft — always marked for manual review."""
    if description:
        return description[:600].strip()
    if title:
        return f"New case: {title}. [NEEDS REVIEW — add details before posting]"
    return "[NEEDS REVIEW — could not detect a title or caption for this URL]"


def build_batch_item_from_url(url: str, settings: dict) -> dict:
    """Best-effort detect a title/caption draft for a pasted/imported batch
    URL. Returns:
      url, title, title_source ("detected"/"needs_review"),
      caption (draft body only), caption_source ("ai"/"template"),
      needs_review (bool), probe_error (str, may be empty)
    """
    try:
        title, title_source, description, probe_error = _detect_title(url, settings)
    except Exception as e:
        title, title_source, description, probe_error = "", "needs_review", "", str(e)

    body = _ai_caption_body(title, description)
    caption_source = "ai" if body else "template"
    if not body:
        body = _template_caption_body(title, description)

    return {
        "url": url,
        "title": title,
        "title_source": title_source,
        "caption": body,
        "caption_source": caption_source,
        "needs_review": title_source == "needs_review" or caption_source == "template",
        "probe_error": probe_error,
    }
