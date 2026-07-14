"""Research Hub: AI-assisted case identification from user-supplied clues.

identify_case() takes whatever the user pasted into the Research Hub search
panel (names, a location, a date, a headline, a URL, free text - any mix,
one per line) and asks the local AI to identify the most likely case.

The AI is never allowed to invent facts. If local identification is
unavailable or times out, identify_case() falls back to a cautious,
Low-confidence search target built only from the clues the user supplied -
it never fabricates victims, suspects, dates, a timeline, aliases, or an
outcome.
"""
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from verdictin60_core.ai import get_ai_timeout, is_timeout_error, ollama_identify

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass
class IdentifiedCase:
    title: str = ""
    aliases: list = field(default_factory=list)
    confidence: str = "Very Low"
    confidence_reason: str = ""
    related_people: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
    victims: list = field(default_factory=list)
    suspects: list = field(default_factory=list)
    outcome: str = ""
    identified: bool = False


def parse_clues(raw_text: str) -> list:
    """Split multi-line/pasted Research Hub input into individual clue fragments."""
    fragments = []
    for line in (raw_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if URL_RE.match(line):
            fragments.append(line)
        else:
            fragments.extend(p.strip() for p in line.split(",") if p.strip())
    return fragments


def _url_search_title(url: str) -> str:
    """Derive a simple, cautious search title from a URL's slug or domain."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path:
        slug = path.rstrip("/").split("/")[-1]
        slug = re.sub(r"\.\w+$", "", slug)
        slug = re.sub(r"[-_]+", " ", slug).strip()
        if slug and not slug.isdigit():
            return slug
    return parsed.netloc.replace("www.", "")


def _fallback_identified_case(clues: list) -> IdentifiedCase:
    """Cautious fallback used when AI identification is unavailable or times out.

    Uses only the user-supplied clues as a search target - never invents
    victims, suspects, dates, a timeline, aliases, or an outcome.
    """
    text_fragments = [c for c in clues if not URL_RE.match(c)]
    url_fragments = [c for c in clues if URL_RE.match(c)]

    if text_fragments:
        title = text_fragments[0]
    elif url_fragments:
        title = _url_search_title(url_fragments[0])
    else:
        title = ""

    return IdentifiedCase(
        title=title,
        confidence="Low",
        confidence_reason=(
            "Local AI identification timed out, so Research Hub is using the "
            "supplied clues as a cautious search target instead of a "
            "confirmed case identification. No facts beyond the pasted "
            "clues are known."
        ),
        identified=bool(title),
    )


def _build_identify_prompt(clues: list) -> str:
    clue_text = "\n".join(f"- {c}" for c in clues)
    return (
        "You are a careful research assistant identifying a real news/legal "
        "case from user-supplied clues. Never invent facts you cannot "
        "support from the clues below. If you cannot identify the case with "
        "reasonable confidence, say so plainly and leave fields empty.\n\n"
        f"Clues:\n{clue_text}\n\n"
        "Respond ONLY with JSON in this exact shape:\n"
        "{\n"
        '  "title": "",\n'
        '  "aliases": [],\n'
        '  "confidence": "High|Medium|Low|Very Low",\n'
        '  "confidence_reason": "",\n'
        '  "related_people": [],\n'
        '  "timeline": [],\n'
        '  "victims": [],\n'
        '  "suspects": [],\n'
        '  "outcome": ""\n'
        "}"
    )


def _parse_identify_response(raw: str, clues: list) -> IdentifiedCase:
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return _fallback_identified_case(clues)
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return _fallback_identified_case(clues)

    title = (data.get("title") or "").strip()
    return IdentifiedCase(
        title=title,
        aliases=data.get("aliases") or [],
        confidence=data.get("confidence") or "Very Low",
        confidence_reason=(data.get("confidence_reason") or "").strip(),
        related_people=data.get("related_people") or [],
        timeline=data.get("timeline") or [],
        victims=data.get("victims") or [],
        suspects=data.get("suspects") or [],
        outcome=(data.get("outcome") or "").strip(),
        identified=bool(title),
    )


def identify_case(raw_clue_text: str) -> IdentifiedCase:
    """Identify the most likely case from Research Hub search-panel input.

    Never invents facts. If the local AI call fails or times out, falls back
    to a Low-confidence search target built only from the supplied clues.
    """
    clues = parse_clues(raw_clue_text)
    if not clues:
        return IdentifiedCase(
            confidence="Very Low",
            confidence_reason="No clues were provided.",
        )

    prompt = _build_identify_prompt(clues)
    try:
        raw = ollama_identify(prompt, timeout=get_ai_timeout("identify"))
    except Exception as exc:
        if is_timeout_error(exc):
            print("[RESEARCH_HUB] identify_case AI call failed: timed out")
        else:
            print(f"[RESEARCH_HUB] identify_case AI call failed: {exc}")
        return _fallback_identified_case(clues)

    return _parse_identify_response(raw, clues)
