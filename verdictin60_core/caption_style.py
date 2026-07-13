"""Official VerdictIn60 caption style — structure, hashtag pool, and constraint
enforcement, added for the Batch tab "Add Videos" redesign (issue #77).

- DEFAULT_HASHTAGS_20: the app's default 20-hashtag pool.
- CTA_LINE / RESEARCH_HEADING / RESEARCH_DIVIDER: the fixed strings every
  caption must contain.
- build_caption_prompt: the AI prompt that asks a model to write a caption in
  the official hook / story / context / CTA / hashtags / research structure,
  using only the supplied facts.
- local_fallback_caption: a deterministic, editable caption built from
  whatever metadata is available, used when AI is unavailable or its output
  fails validation. Always flagged for manual review.
- enforce_caption_constraints: post-processes any caption (AI or fallback) so
  it always has the CTA, exactly 20 hashtags, a Research & Verification
  section, and stays under the 2,200 character Buffer-compatible limit —
  regardless of what the model actually produced.
"""
import re

from verdictin60_core.captions import MAX_CAPTION_LENGTH

CTA_LINE = "Follow @verdictin60 for daily true crime \U0001fa78\U0001f52a"
RESEARCH_HEADING = "Research & Verification"
RESEARCH_DIVIDER = "━" * 17

# The official VerdictIn60 default hashtag pool (issue #77). Used verbatim
# when a caption has none, and to pad/dedupe when it has the wrong count.
DEFAULT_HASHTAGS_20 = [
    "truecrime", "crime", "criminal", "mystery", "history", "unsolved",
    "investigation", "court", "justice", "forensics", "documentary",
    "crimefacts", "truecrimecommunity", "facts", "law", "coldcase",
    "storytelling", "darkhistory", "reels", "verdictin60",
]

_HASHTAG_RE = re.compile(r'(?<!\w)#\w+')


def build_caption_prompt(title: str, metadata: dict, source_url: str = "") -> str:
    """Prompt an AI model to write a caption in the official VerdictIn60 structure,
    using only the facts we actually gathered (never invent sources)."""
    metadata = metadata or {}
    facts = []
    if metadata.get("description"):
        facts.append(f"Description/summary found at the source: {metadata['description'][:1200]}")
    if metadata.get("uploader"):
        facts.append(f"Source channel/uploader: {metadata['uploader']}")
    if metadata.get("page_title"):
        facts.append(f"Source page title: {metadata['page_title']}")
    if source_url:
        facts.append(f"Source URL: {source_url}")
    facts_block = "\n".join(facts) if facts else (
        "No source metadata could be extracted — rely only on the case title, "
        "and clearly keep the story section short rather than inventing details."
    )

    return f"""You are writing an Instagram caption for VerdictIn60, a true-crime documentary account.

Case title: {title}

Known facts (do not invent anything beyond this):
{facts_block}

Write the caption using EXACTLY this structure, in this order:

1. HOOK - 1-2 lines. Immediately grabs attention, usually the most shocking
   VERIFIED fact. Must still be factual and sourced. No speculation.
2. THE STORY - chronological, concise, easy to read. Short paragraphs of
   1-3 sentences. Only verified facts. Avoid speculation and avoid graphic
   detail beyond what's necessary. State the outcome if known (arrest,
   conviction, rescue, unresolved case, etc.).
3. CONTEXT - briefly explain why the case became significant (historical,
   legal, or social context where appropriate).
4. Then this exact line, on its own:
{CTA_LINE}
5. Then EXACTLY 20 relevant hashtags, space-separated, all on one line,
   each starting with #.
6. Then this exact block, with the bullet points filled in from the facts
   above (write "Source verification pending - review before publishing"
   for any bullet you are not confident about instead of inventing one):
{RESEARCH_DIVIDER}
{RESEARCH_HEADING}
Official:
• ...
Reporting:
• ...

Writing rules:
- Maximum 2,200 characters total.
- Never invent dialogue, thoughts, motives, psychological claims, or sources.
- If a detail is disputed, say so clearly instead of picking a side.
- Avoid exaggerated phrases like "the most evil ever".
- Tone: professional, cinematic, concise, credible - a mini documentary,
  never clickbait. The ending should feel informative, not sensational.
"""


def local_fallback_caption(title: str, metadata: dict, source_url: str = "") -> str:
    """A deterministic, fully-structured caption built without AI, for when no
    model is available or the AI output failed validation. Always needs a
    human review pass before it's scheduled — callers should flag it as such."""
    metadata = metadata or {}
    display_title = (title or "").strip() or "This case"
    description = (metadata.get("description") or metadata.get("page_title") or "").strip()

    hook = f"{display_title} is a case VerdictIn60 is currently verifying."

    if description:
        snippet = description[:400].rsplit(" ", 1)[0]
        if len(description) > 400:
            snippet += "…"
        story = snippet
    else:
        story = (
            "Full details for this case are still being researched. This caption "
            "was generated automatically from limited source data and needs a "
            "manual fact-check before it goes out."
        )

    context = (
        "VerdictIn60 covers true-crime cases for their historical, legal, or "
        "social significance - this entry is queued for editorial review to "
        "confirm that context before publishing."
    )

    hashtags_line = " ".join(f"#{tag}" for tag in DEFAULT_HASHTAGS_20)

    reporting = f"• Source: {source_url}" if source_url else "• Source: local file, no URL provided"
    research = (
        f"{RESEARCH_DIVIDER}\n{RESEARCH_HEADING}\nOfficial:\n"
        f"• Source verification pending - review before publishing\n"
        f"Reporting:\n{reporting}"
    )

    return "\n\n".join([hook, story, context, CTA_LINE, hashtags_line, research])


def _is_hashtag_line(line: str) -> bool:
    tokens = line.split()
    return bool(tokens) and all(t.startswith("#") for t in tokens)


def _split_research_section(text: str) -> tuple:
    idx = text.find(RESEARCH_HEADING)
    if idx == -1:
        return text.strip(), ""
    start = idx
    divider_idx = text.rfind(RESEARCH_DIVIDER, 0, idx)
    if divider_idx != -1 and text[divider_idx:idx].strip() == RESEARCH_DIVIDER:
        start = divider_idx
    return text[:start].rstrip(), text[start:].strip()


def _default_research_section(source_url: str = "") -> str:
    reporting = f"• Source: {source_url}" if source_url else "• Source verification pending - review before publishing"
    return (
        f"{RESEARCH_DIVIDER}\n{RESEARCH_HEADING}\nOfficial:\n"
        f"• Source verification pending - review before publishing\n"
        f"Reporting:\n{reporting}"
    )


def _normalize_hashtags(found: list) -> list:
    """Dedupe (case-insensitive) preserving order, then pad/truncate to exactly 20."""
    seen = set()
    result = []
    for tag in found:
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            result.append(tag)
    for tag in DEFAULT_HASHTAGS_20:
        if len(result) >= 20:
            break
        full = f"#{tag}"
        if full.lower() not in seen:
            seen.add(full.lower())
            result.append(full)
    return result[:20]


def _trim_to_length(body: str, hashtags_line: str, research: str) -> str:
    full = f"{body}\n\n{hashtags_line}\n\n{research}".strip()
    if len(full) <= MAX_CAPTION_LENGTH:
        return full

    # Trim the body's inner paragraphs first (keep the hook first and the CTA last).
    paragraphs = body.split("\n\n")
    while len(paragraphs) > 2:
        candidate = "\n\n".join(paragraphs)
        if len(candidate) + len(hashtags_line) + len(research) + 4 <= MAX_CAPTION_LENGTH:
            break
        del paragraphs[-2]
    body = "\n\n".join(paragraphs)
    full = f"{body}\n\n{hashtags_line}\n\n{research}".strip()

    if len(full) > MAX_CAPTION_LENGTH:
        # Last resort: hard-truncate the research section's bullet text.
        overflow = len(full) - MAX_CAPTION_LENGTH
        research = research[: max(0, len(research) - overflow)].rstrip()
        full = f"{body}\n\n{hashtags_line}\n\n{research}".strip()

    return full[:MAX_CAPTION_LENGTH]


def enforce_caption_constraints(caption: str, source_url: str = "") -> str:
    """Guarantee the CTA, exactly 20 hashtags, a Research & Verification
    section, and the 2,200 character limit, no matter what the caller passed
    in (AI output, the local fallback template, or a user edit)."""
    text = re.sub(r'<think>.*?</think>', '', caption or "", flags=re.DOTALL | re.IGNORECASE).strip()

    body, research = _split_research_section(text)
    if not research:
        research = _default_research_section(source_url)

    found_hashtags = _HASHTAG_RE.findall(text)
    body = "\n".join(ln for ln in body.splitlines() if not _is_hashtag_line(ln)).strip()

    if not body:
        body = f"{(source_url or 'This case').strip()} is a case VerdictIn60 is currently verifying."

    if CTA_LINE.lower() not in body.lower():
        body = f"{body}\n\n{CTA_LINE}"

    hashtags_line = " ".join(_normalize_hashtags(found_hashtags))

    return _trim_to_length(body, hashtags_line, research)
