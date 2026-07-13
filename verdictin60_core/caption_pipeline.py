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


def generate_case_caption(title: str, metadata: dict, source_url: str, log_lines: list) -> tuple:
    """Return (caption, status) where status is READY or NEEDS_REVIEW.

    Tries the configured AI provider (Ollama by default, NVIDIA NIM if the
    user has enabled Cloud fallback/only — see ai_task_ready/ai_generate) and
    validates its output against the official structure. Falls back to a
    deterministic local template — always flagged NEEDS_REVIEW — if AI is
    unavailable or its output doesn't hold up.
    """
    metadata = metadata or {}
    caption = ""

    if ai_task_ready("caption"):
        try:
            prompt = build_caption_prompt(title, metadata, source_url)
            caption = ai_generate(prompt, task="caption", num_predict=1500)
        except Exception as e:
            log_lines.append(f"AI caption generation failed: {e}")
            caption = ""
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
    return caption, (NEEDS_REVIEW if needs_review else READY)
