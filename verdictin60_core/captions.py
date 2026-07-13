"""Caption validation/counting helpers, moved from app.py (Phase 1 refactor, no behavior change).

- caption_needs_fallback: check length, hashtag count, required sections, and
  CTA presence in an AI-generated caption, returning a reason string (or ""
  when the caption passes) so the caller can decide whether to fall back.
"""
import re

# Buffer-compatible ceiling for the official VerdictIn60 caption style (issue #77).
MAX_CAPTION_LENGTH = 2200


def caption_needs_fallback(caption: str) -> str:
    """Return a reason when an AI caption is clearly incomplete or unusable."""
    # Strip any <think>...</think> blocks (qwen3 and similar thinking models)
    text = re.sub(r'<think>.*?</think>', '', caption, flags=re.DOTALL | re.IGNORECASE).strip()
    if not text:
        return "empty"
    if len(text) < 280:
        return "too short"
    if len(text) > MAX_CAPTION_LENGTH:
        return f"too long ({len(text)} chars)"
    if "Research & Verification" not in text:
        return "missing Research & Verification"
    hashtag_count = len(re.findall(r'(?<!\w)#\w+', text))
    if hashtag_count != 20:
        return f"wrong hashtag count ({hashtag_count})"
    if "Follow @VerdictIn60" not in text and "Follow @verdictin60" not in text:
        return "missing CTA"
    prose = "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    ).strip()
    if prose and prose[-1] not in ".!?":
        return "unfinished sentence"
    return ""
