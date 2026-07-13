"""Per-item caption generation for the Batch tab "Add Videos" workflow (issue #77).

Ties together the existing AI provider stack (verdictin60_core.ai — which
already respects the cost/quota safety guard in provider_guard.py and never
repeatedly hits a paid/cloud provider after a quota/rate-limit/auth/timeout
failure) with the official VerdictIn60 caption structure in caption_style.py.

generate_case_caption never raises — an AI failure (unavailable, timed out,
malformed output) is caught and treated the same as "no AI available": it
always returns a usable, structurally-valid caption (falling back to a local
template when needed) and flags whether a human still needs to review it
before scheduling.
"""
from verdictin60_core.ai import ai_generate, ai_task_ready
from verdictin60_core.captions import caption_needs_fallback
from verdictin60_core.caption_style import (
    build_caption_prompt, local_fallback_caption, enforce_caption_constraints,
)

READY = "ready"
NEEDS_REVIEW = "needs_review"

# Plain-English categories surfaced on a Needs Review batch row (issue #79) —
# broader buckets than the internal caption_needs_fallback() reason strings,
# so a non-technical user can tell at a glance why a row needs manual work.
REASON_AI_UNAVAILABLE = "AI unavailable"
REASON_METADATA_UNAVAILABLE = "metadata unavailable"
REASON_INSTAGRAM_BLOCKED = "Instagram blocked metadata"
REASON_SOURCE_PENDING = "source verification pending"


def _classify_review_reason(source_url: str, metadata: dict, ai_ready: bool) -> str:
    """Map the low-level cause of a NEEDS_REVIEW flag to one of the review
    reason categories shown on the batch row."""
    has_metadata = bool(
        metadata.get("description") or metadata.get("title") or metadata.get("page_title")
    )
    if not has_metadata and "instagram.com" in (source_url or "").lower():
        return REASON_INSTAGRAM_BLOCKED
    if not ai_ready:
        return REASON_AI_UNAVAILABLE
    if not has_metadata:
        return REASON_METADATA_UNAVAILABLE
    return REASON_SOURCE_PENDING


def generate_case_caption(title: str, metadata: dict, source_url: str, log_lines: list) -> tuple:
    """Return (caption, status, review_reason) where status is READY or
    NEEDS_REVIEW, and review_reason is a short plain-English category (e.g.
    "AI unavailable", "metadata unavailable") explaining why — empty when
    status is READY.

    Tries the configured AI provider (Ollama by default, NVIDIA NIM if the
    user has enabled Cloud fallback/only — see ai_task_ready/ai_generate) and
    validates its output against the official structure. Falls back to a
    deterministic local template — always flagged NEEDS_REVIEW — if AI is
    unavailable or its output doesn't hold up.
    """
    metadata = metadata or {}
    caption = ""
    ai_ready = ai_task_ready("caption")

    if ai_ready:
        try:
            prompt = build_caption_prompt(title, metadata, source_url)
            caption = ai_generate(prompt, task="caption", num_predict=1500)
        except Exception as e:
            log_lines.append(f"AI caption generation failed: {e}")
            caption = ""
            ai_ready = False  # a failed call is treated the same as "no AI available"
    else:
        log_lines.append(
            "AI caption task not ready (no local model installed / no cloud "
            "provider configured) - using local fallback template"
        )

    reason = caption_needs_fallback(caption) if caption else "no AI output available"
    needs_review = bool(reason)

    if reason:
        log_lines.append(f"Using local fallback caption template ({reason})")
        caption = local_fallback_caption(title, metadata, source_url)
    elif not metadata.get("description") and not metadata.get("page_title"):
        # The AI wrote a well-formed caption, but we had almost no source
        # material to check it against - flag it rather than trust it blindly.
        needs_review = True
        log_lines.append("Very little source metadata available - flagging AI caption for manual review")

    caption = enforce_caption_constraints(caption, source_url)

    review_reason = _classify_review_reason(source_url, metadata, ai_ready) if needs_review else ""
    return caption, (NEEDS_REVIEW if needs_review else READY), review_reason
