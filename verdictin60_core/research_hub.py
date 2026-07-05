"""Research Hub — multi-clue case identification, budgeted source gathering,
and archive recovery for the "Research Hub" tab (issue #52).

- parse_clues: split free-form pasted text into URLs (grouped by platform),
  text fragments, and year mentions.
- identify_case: ask the local AI to identify the most likely real case from
  the pasted clues (title/aliases/confidence/reasoning/victims/suspects/
  timeline/outcome). Never invents facts. On AI timeout/failure, falls back
  to a Low-confidence search target built only from the user's own clues.
- check_wayback_availability / manual_archive_links / recover_archives:
  Wayback Machine archive recovery, plus manual lookup links for
  Archive.today / Memento / CachedView (no stable, scrape-safe API).
- investigate: orchestrates identification, budgeted source gathering
  (reuses verdictin60_core.research.gather_verification_sources), and
  archive recovery, targeting a ~60-90s total investigation.
- generate_caption / export_markdown: turn an investigation result into a
  caption (grounded only in verified sources) or a Markdown research report.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from verdictin60_core.ai import ai_identify, ai_generate, is_timeout_error
from verdictin60_core.captions import caption_needs_fallback
from verdictin60_core.research import (
    fetch_wikipedia_summary, gather_verification_sources,
    format_sources_for_prompt, format_blocked_sources_for_prompt,
    verification_confidence, build_verified_fact_sheet, source_section_for_caption,
)

DEFAULT_HASHTAGS = (
    "#truecrime #verdictin60 #truecrimecommunity #coldcase #crimejunkie #justice "
    "#realcrimecases #crimeawareness #crimearchive #truecrimestories #crimeanalysis "
    "#lawandcrime #casefile #truecrimeobsessed #victimsmatter #crimebreakdown "
    "#truecrimefacts #truestoryreels #crimecommunity #crimehistory"
)

DEFAULT_DEADLINE_SECONDS = 75
DEFAULT_MAX_SOURCES = 20

_PLATFORM_HOSTS = (
    ("Instagram", ("instagram.com",)),
    ("TikTok", ("tiktok.com",)),
    ("YouTube", ("youtube.com", "youtu.be")),
    ("X (Twitter)", ("twitter.com", "x.com")),
    ("Facebook", ("facebook.com", "fb.com")),
    ("Reddit", ("reddit.com",)),
)


# ─────────────────────────────────────────────────────────────────────────────
# Clue parsing
# ─────────────────────────────────────────────────────────────────────────────

def _platform_for_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    for label, hosts in _PLATFORM_HOSTS:
        if any(h in host for h in hosts):
            return label
    return "Other"


def parse_clues(raw_text: str) -> dict:
    """Split pasted clue text (one or more names/URLs/locations/dates/keywords,
    one per line or free text) into URLs grouped by platform, plain-text
    fragments, and any year mentions."""
    raw_text = (raw_text or "").strip()
    urls = re.findall(r'https?://\S+', raw_text)
    urls = [u.rstrip('.,;:)"\'') for u in urls]
    text_without_urls = re.sub(r'https?://\S+', ' ', raw_text)
    text_lines = [l.strip() for l in text_without_urls.splitlines() if l.strip()]
    years = re.findall(r'\b(?:18|19|20)\d{2}\b', raw_text)

    platform_urls: dict = {}
    for u in urls:
        platform_urls.setdefault(_platform_for_url(u), []).append(u)

    return {
        "raw_text": raw_text,
        "urls": urls,
        "platform_urls": platform_urls,
        "text_lines": text_lines,
        "free_text": "\n".join(text_lines),
        "years": years,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI case identification
# ─────────────────────────────────────────────────────────────────────────────

_IDENTIFY_PROMPT_TEMPLATE = """You are a cautious true-crime research assistant. A user has pasted clues \
(names, locations, dates, keywords, a headline, or social/media URLs) that may refer to a real case.

Clues:
---
{clues}
---

Identify the single most likely real case these clues refer to.

CRITICAL OUTPUT FORMAT — follow exactly:
- Respond with ONLY a single valid JSON object. Nothing else.
- No markdown. No code fences (no ``` of any kind).
- No explanation, preamble, reasoning, or commentary before or after the JSON.
- Do not think out loud — output only the final JSON object. Keep every field short so the whole \
response fits in a small output budget; do not pad or elaborate.
- The JSON object must contain exactly these keys:
{{
  "identified": true or false,
  "case_title": "the person's name or case title, or empty string if you cannot identify one",
  "aliases": ["known aliases, nicknames, or alternate spellings — at most 3, empty list if none"],
  "confidence": "High" or "Medium" or "Low" or "Very Low",
  "confidence_reason": "exactly one short sentence explaining the confidence level",
  "victims": ["victim names — at most 3, empty list if unknown"],
  "suspects": ["suspect names — at most 3, empty list if unknown"],
  "related_people": ["other related people — at most 3, empty list if none"],
  "timeline": ["short chronological bullet points — at most 5, empty list if unknown"],
  "outcome": "legal outcome/verdict if known, else empty string — one short sentence"
}}

Rules:
- Never invent facts. Only include a detail if you are reasonably confident it is real and consistent with the clues.
- If you cannot identify a specific real case with reasonable confidence, set "identified" to false, \
"confidence" to "Very Low", and leave victims/suspects/timeline/outcome empty — do not guess a case just to have an answer.
- Respect every list-length limit above. Do not exceed it even if more items are known.

Return only the JSON object described above — no other text.
"""


def _build_identify_prompt(clues: dict) -> str:
    lines = []
    if clues["free_text"]:
        lines.append(clues["free_text"][:1800])
    for platform, urls in clues["platform_urls"].items():
        for u in urls[:5]:
            lines.append(f"{platform} URL: {u}")
    clue_block = "\n".join(lines)[:2200] or "(no text clues — URLs only, see above)"
    return _IDENTIFY_PROMPT_TEMPLATE.format(clues=clue_block)


def _strip_code_fences(text: str) -> str:
    """Strip a wrapping ```/```json markdown code fence, if present. Some
    models (notably NVIDIA NIM) wrap JSON in fences despite being told not to."""
    text = text.strip()
    match = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Tolerate a fence on only one side (model forgot the closing/opening fence).
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


def _find_first_balanced_region(text: str, open_ch: str, close_ch: str):
    """Scan for the first balanced open_ch...close_ch region, tolerating
    stray prose or reasoning text before/after it. Brace-depth aware so
    braces/brackets inside JSON string values don't break the scan. Returns
    the raw substring (not parsed), or None if no balanced region exists."""
    search_from = 0
    while True:
        start = text.find(open_ch, search_from)
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        search_from = start + 1


class _IdentifyParseError(Exception):
    """Raised when the identify AI response can't be parsed. The message is
    always one of a small set of safe, specific reasons — it never includes
    the raw response text (that's logged separately as a sanitized preview)."""


_SECRET_LIKE_PATTERNS = (
    re.compile(r'(?i)bearer\s+[A-Za-z0-9\-_.]+'),
    re.compile(r'(?i)(api[_-]?key|authorization)("|\')?\s*[:=]\s*("|\')?[A-Za-z0-9\-_.]{8,}'),
)


def _sanitize_ai_response_preview(raw: str, limit: int = 500) -> str:
    """Build a short, safe preview of a raw AI response for debug logging
    when identify JSON parsing fails. Callers must only pass the model's own
    response text — never the prompt or request headers. The redaction below
    is defense-in-depth in case a model ever echoes something secret-shaped."""
    text = re.sub(r'\s+', ' ', raw or "").strip()
    for pattern in _SECRET_LIKE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _strip_reasoning_labels(text: str) -> str:
    """Strip a leading/trailing 'Reasoning:' / 'Answer:' style label that some
    models prepend or append despite being told to return only JSON."""
    label = r'(?:reasoning|answer|response|output|result)\s*:\s*'
    text = re.sub(rf'^\s*{label}', '', text, flags=re.IGNORECASE)
    text = re.sub(rf'\s*{label}$', '', text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_quotes_if_safe(text: str) -> str:
    """Best-effort normalize single-quoted, Python-dict-style output into
    double-quoted JSON. Only attempted when the text has no double quotes at
    all, so real apostrophes inside double-quoted string values are never
    touched."""
    if '"' in text or "'" not in text:
        return text
    return text.replace("'", '"')


def _decode_json_ish(text: str):
    """Try to decode `text` as JSON directly, then fall back to scanning for
    the first balanced {...} region. Returns (data, found_object_shape) —
    found_object_shape is True whenever an object-like region was located,
    even if it ultimately failed to decode (used to pick a specific error)."""
    try:
        return json.loads(text), True
    except Exception:
        pass
    region = _find_first_balanced_region(text, '{', '}')
    if region is None:
        return None, False
    try:
        return json.loads(region), True
    except Exception:
        return None, True


def _repair_truncated_json_object(text: str):
    """Conservative repair for an identify response that starts with '{' but
    was cut off before a balanced closing '}' — typically the model's output
    hit its token limit mid-object. Closes an unterminated string (if any),
    trims a dangling trailing key/value fragment that has no value, then
    closes whatever objects/arrays were still open and tries to parse.

    Returns the parsed dict, or None if the repair still doesn't produce
    valid JSON (the caller then falls back to the clue-based result — this
    never raises and never invents field values, it only closes punctuation
    the model didn't get to emit)."""
    stack = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in '{[':
            stack.append(ch)
        elif ch in '}]' and stack:
            stack.pop()

    if not stack:
        # Already balanced (or broken in some other way) — not a truncation case.
        return None

    repaired = text + '"' if in_string else text
    for _ in range(4):
        # Only strip a dangling *key* with no value at all (comma, quoted
        # key, colon, then nothing) — the colon is required so a complete
        # trailing string that's a valid array/object value (no colon after
        # it) is never mistaken for a dangling fragment and dropped.
        trimmed = re.sub(r',\s*"[^"]*"\s*:\s*$', '', repaired)
        trimmed = re.sub(r',\s*$', '', trimmed)
        if trimmed == repaired:
            break
        repaired = trimmed

    for opener in reversed(stack):
        repaired += ']' if opener == '[' else '}'

    try:
        data = json.loads(repaired)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _extract_tool_call_arguments(data: dict):
    """Pull the first object-like `arguments` payload out of an OpenAI/NVIDIA
    style tool-call response, e.g.
    {"tool_calls": [{"function": {"arguments": "{...}"}}]}."""
    calls = data.get("tool_calls")
    if not isinstance(calls, list):
        return None
    for call in calls:
        fn = call.get("function") if isinstance(call, dict) else None
        args = fn.get("arguments") if isinstance(fn, dict) else None
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        elif isinstance(args, dict):
            return args
    return None


def _parse_identify_json(raw: str) -> dict:
    """Parse the AI's identify response into a dict, tolerating real-world
    formatting deviations: code fences, stray reasoning text, JSON arrays,
    single-quoted JSON, and tool-call style wrapper payloads.

    Raises _IdentifyParseError with one of: "no JSON object found",
    "JSON decode error", "missing required fields", "unexpected schema".
    Never includes the raw response text in the exception.
    """
    if not raw or not raw.strip():
        raise _IdentifyParseError("no JSON object found")

    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()
    text = _strip_code_fences(text)
    text = _strip_reasoning_labels(text)
    if not text:
        raise _IdentifyParseError("no JSON object found")

    data, found_object_shape = _decode_json_ish(text)
    if data is None:
        normalized = _normalize_quotes_if_safe(text)
        if normalized != text:
            data, found_normalized_shape = _decode_json_ish(normalized)
            found_object_shape = found_object_shape or found_normalized_shape

    if data is None and text.startswith('{'):
        # Text starts an object but no balanced '}' was found anywhere in it —
        # likely truncated by the model's max_tokens limit. Try a conservative
        # repair (close the dangling string/array/object) before giving up.
        repaired = _repair_truncated_json_object(text)
        if repaired is not None:
            data = repaired
            found_object_shape = True

    if isinstance(data, dict) and "tool_calls" in data and (
            "identified" not in data or "case_title" not in data):
        tool_data = _extract_tool_call_arguments(data)
        if tool_data is not None:
            data = tool_data

    if data is None:
        raise _IdentifyParseError("JSON decode error" if found_object_shape else "no JSON object found")

    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict)), None)

    if not isinstance(data, dict):
        raise _IdentifyParseError("unexpected schema")

    if "identified" not in data or "case_title" not in data:
        raise _IdentifyParseError("missing required fields")

    return data


def _str_list(data: dict, key: str) -> list:
    v = data.get(key)
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()][:12]


def _normalize_identified_case(data: dict) -> dict:
    identified = bool(data.get("identified")) and bool(str(data.get("case_title", "")).strip())
    if not identified:
        return {
            "identified": False,
            "case_title": "",
            "aliases": [],
            "confidence": "Very Low",
            "confidence_reason": (str(data.get("confidence_reason", "")).strip()[:500]
                                  or "Confidence was too low to identify a specific case from the clues provided."),
            "victims": [], "suspects": [], "related_people": [], "timeline": [], "outcome": "",
            "fallback": False,
        }
    confidence = re.sub(r'\s+', ' ', str(data.get("confidence", "")).strip()).title()
    if confidence not in ("High", "Medium", "Low", "Very Low"):
        confidence = "Low"
    return {
        "identified": True,
        "case_title": str(data.get("case_title", "")).strip()[:200],
        "aliases": _str_list(data, "aliases"),
        "confidence": confidence,
        "confidence_reason": str(data.get("confidence_reason", "")).strip()[:500],
        "victims": _str_list(data, "victims"),
        "suspects": _str_list(data, "suspects"),
        "related_people": _str_list(data, "related_people"),
        "timeline": _str_list(data, "timeline"),
        "outcome": str(data.get("outcome", "")).strip()[:500],
        "fallback": False,
    }


def _title_from_url(url: str) -> str:
    """Derive a plain-text search title from a URL's slug/domain — never
    invents anything, just reformats the URL itself."""
    parsed = urllib.parse.urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    slug = path_parts[-1] if path_parts else ""
    slug = re.sub(r'\.(html?|php|aspx?)$', '', slug, flags=re.I)
    slug = re.sub(r'[-_]+', ' ', slug).strip()
    if len(slug) >= 3 and not slug.replace(" ", "").isdigit():
        return slug.title()[:120]
    domain = parsed.netloc.lower().lstrip("www.")
    return domain or url[:80]


def _cautious_title_from_clues(clues: dict) -> str:
    if clues["text_lines"]:
        return clues["text_lines"][0][:120]
    if clues["urls"]:
        return _title_from_url(clues["urls"][0])
    return ""


def _fallback_identified_case(clues: dict, timed_out: bool) -> dict:
    """Used when local AI case identification times out or otherwise fails.

    Never invents victims, suspects, dates, timeline, aliases, or outcome —
    uses only the user-supplied clues (first text fragment, or a URL
    slug/domain when only a URL was pasted) as a cautious Low-confidence
    search target so Research Hub can still gather and display sources.
    """
    title = _cautious_title_from_clues(clues)
    why = "timed out" if timed_out else "failed"
    reason = (
        f"Local AI identification {why}, so Research Hub is using the supplied clues as a "
        "cautious search target instead of a confirmed case identification. "
        "No facts beyond the pasted clues are known."
    )
    return {
        "identified": bool(title),
        "case_title": title,
        "aliases": [],
        "confidence": "Low" if title else "Very Low",
        "confidence_reason": reason,
        "victims": [], "suspects": [], "related_people": [], "timeline": [], "outcome": "",
        "fallback": True,
    }


def identify_case(raw_clue_text: str) -> dict:
    """Identify the most likely case from pasted clues via the local AI.

    Returns a dict with identified/case_title/aliases/confidence/
    confidence_reason/victims/suspects/related_people/timeline/outcome.
    Never invents facts; states plainly when confidence is too low, and — on
    AI timeout/failure — falls back to a clue-based Low-confidence search
    target rather than ending with "no case identified".
    """
    clues = parse_clues(raw_clue_text)
    if not clues["free_text"] and not clues["urls"]:
        return {
            "identified": False, "case_title": "", "aliases": [],
            "confidence": "Very Low",
            "confidence_reason": "No clues were provided.",
            "victims": [], "suspects": [], "related_people": [], "timeline": [], "outcome": "",
            "fallback": False,
        }
    prompt = _build_identify_prompt(clues)
    raw = ""
    try:
        raw = ai_identify(prompt)
        data = _parse_identify_json(raw)
    except _IdentifyParseError as e:
        preview = _sanitize_ai_response_preview(raw)
        print(f"[RESEARCH_HUB] identify_case AI response was not valid JSON ({e}); "
              f"raw_len={len(raw)}; response preview: {preview!r}")
        return _fallback_identified_case(clues, timed_out=False)
    except Exception as e:
        timed_out = is_timeout_error(e)
        print(f"[RESEARCH_HUB] identify_case AI call failed: {'timed out' if timed_out else e}")
        return _fallback_identified_case(clues, timed_out)
    return _normalize_identified_case(data)


# ─────────────────────────────────────────────────────────────────────────────
# Archive recovery
# ─────────────────────────────────────────────────────────────────────────────

def check_wayback_availability(url: str, timeout: int = 8):
    """Free Internet Archive Wayback availability API — no API key needed.
    Returns {"provider", "archive_url", "timestamp"} or None."""
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "VerdictIn60/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        snap = (data.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available") and snap.get("url"):
            return {
                "provider": "Wayback Machine",
                "archive_url": snap["url"],
                "timestamp": snap.get("timestamp", ""),
            }
    except Exception as e:
        print(f"[RESEARCH_HUB] Wayback lookup failed for {url[:80]}: {e}")
    return None


def manual_archive_links(url: str) -> dict:
    """Manual lookup links for archive services with no stable, scrape-safe
    API (Archive.today/Archive.is, Memento Time Travel, CachedView). Research
    Hub never guesses whether these have a copy — it only links out."""
    return {
        "Archive.today": f"https://archive.ph/{url}",
        "Memento Time Travel": f"https://timetravel.mementoweb.org/timemap/link/{url}",
        "CachedView": "https://cachedview.nl/",
    }


def recover_archives(sources: list, deadline_seconds: float = None, max_lookups: int = 12) -> dict:
    """Attempt Wayback Machine recovery for every blocked/inaccessible source,
    bounded by a time budget and a lookup cap. Recovered pages are labeled
    with their archive provider; everything else gets manual lookup links for
    the other archive services instead of a guessed result."""
    t_start = time.time()
    attempted = 0
    recovered = 0
    for src in sources:
        if not src.get("blocked"):
            continue
        if attempted >= max_lookups:
            break
        if deadline_seconds is not None and (time.time() - t_start) >= deadline_seconds:
            break
        attempted += 1
        info = check_wayback_availability(src["url"])
        if info:
            src["archived"] = True
            src["archive_provider"] = info["provider"]
            src["archive_url"] = info["archive_url"]
            recovered += 1
        else:
            src["archived"] = False
            src["manual_archive_links"] = manual_archive_links(src["url"])
    return {
        "attempted": attempted,
        "recovered": recovered,
        "elapsed_seconds": round(time.time() - t_start, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Investigation orchestration
# ─────────────────────────────────────────────────────────────────────────────

def investigate(raw_clue_text: str, deadline_seconds: int = DEFAULT_DEADLINE_SECONDS,
                max_sources: int = DEFAULT_MAX_SOURCES) -> dict:
    """Run a full Research Hub pass: identify the case, gather sources under a
    strict time/count budget, then recover archives for blocked sources.

    Targets ~60-90s total: `deadline_seconds` bounds source gathering, and
    archive recovery is capped to whatever time remains (or 20s, whichever is
    smaller) so a slow run still finishes close to the target window.
    """
    t_start = time.time()
    clues = parse_clues(raw_clue_text)
    case = identify_case(raw_clue_text)

    result = {
        "clues": clues,
        "case": case,
        "sources": [],
        "stats": {"elapsed_seconds": 0.0, "sources_checked": 0,
                  "skipped_slow_or_blocked": 0, "stopped_reason": ""},
        "archive": {"attempted": 0, "recovered": 0, "elapsed_seconds": 0.0},
        "source_confidence": "Very low",
        "source_confidence_reason": "No case title was available to search.",
        "wiki_title": "",
        "elapsed_seconds": 0.0,
    }
    if not case.get("case_title"):
        result["stats"]["stopped_reason"] = "no case title available to search"
        result["elapsed_seconds"] = round(time.time() - t_start, 1)
        return result

    wiki_facts, wiki_title = fetch_wikipedia_summary(case["case_title"])
    original_context = clues["free_text"] or case["case_title"]

    src_stats: dict = {}
    sources = gather_verification_sources(
        case["case_title"], original_context, wiki_title, wiki_facts,
        deadline_seconds=deadline_seconds, max_sources=max_sources, stats=src_stats,
    )
    result["sources"] = sources
    result["stats"] = src_stats
    result["wiki_title"] = wiki_title

    remaining = max(5.0, deadline_seconds - (time.time() - t_start))
    archive_deadline = min(remaining, 20.0)
    result["archive"] = recover_archives(sources, deadline_seconds=archive_deadline)

    confidence_label, confidence_reason = verification_confidence(sources)
    result["source_confidence"] = confidence_label
    result["source_confidence_reason"] = confidence_reason
    result["elapsed_seconds"] = round(time.time() - t_start, 1)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Caption generation
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_caption(case: dict, sources: list) -> str:
    title = case.get("case_title") or "This case"
    research = source_section_for_caption(sources)
    body = "\n\n".join([
        f"VerdictIn60: {title}",
        f"{title} is the subject of this investigation.",
        (
            "With limited accessible source material, the most responsible way to "
            "cover this case is to separate confirmed facts from online speculation "
            "and avoid repeating details that cannot be independently checked."
        ),
        "What detail do you think should be verified first before people share this story?",
    ])
    return f"{body}\n\n{research}\n\nFollow @VerdictIn60 for daily true crime.\n\n{DEFAULT_HASHTAGS}"


def generate_caption(result: dict) -> str:
    """Generate a caption grounded only in this investigation's verified
    sources. Never invents facts; falls back to a cautious template if the
    local AI is unavailable or its output doesn't pass validation."""
    case = result.get("case", {})
    sources = result.get("sources", [])
    title = case.get("case_title") or "Unidentified Case"
    source_section = source_section_for_caption(sources)
    source_prompt_text = format_sources_for_prompt(sources)
    blocked_prompt_text = format_blocked_sources_for_prompt(sources)
    fact_sheet = build_verified_fact_sheet(title, sources)
    confidence_label = result.get("source_confidence", "Very low")
    confidence_reason = result.get("source_confidence_reason", "")

    prompt = (
        "You are writing a VerdictIn60 Instagram caption from Research Hub findings.\n\n"
        f"Primary subject: {title}\n"
        f"Verification confidence: {confidence_label} — {confidence_reason}\n\n"
        "Use only the verified fact sheet and accessible sources below. Do not invent names, "
        "dates, motives, quotes, locations, charges, sentences, or emotional details. If a "
        "detail is not supported, omit it or phrase cautiously.\n\n"
        f"Verified fact sheet:\n{fact_sheet}\n\n"
        f"Accessible sources:\n{source_prompt_text[:6500]}\n\n"
        f"Blocked but discovered sources:\n{blocked_prompt_text[:1800]}\n\n"
        "Requirements:\n"
        "- Strong hook, short dramatic paragraphs, chronological storytelling.\n"
        "- Clear respectful tone; no unsupported dramatic claims.\n"
        "- Add one engagement question near the end.\n"
        "- Include: Follow @VerdictIn60 for daily true crime.\n"
        "- End with this exact Research & Verification section:\n"
        f"{source_section}\n"
        "- Include exactly 20 relevant hashtags at the end.\n"
        "- Do not list Wikipedia in Research & Verification.\n"
        "- Return only the caption."
    )
    try:
        raw = ai_generate(prompt, task="research")
        reason = caption_needs_fallback(raw)
        if not reason:
            return re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()
        print(f"[RESEARCH_HUB] generated caption needs fallback: {reason}")
    except Exception as e:
        print(f"[RESEARCH_HUB] caption generation failed: {e}")
    return _fallback_caption(case, sources)


# ─────────────────────────────────────────────────────────────────────────────
# Markdown export
# ─────────────────────────────────────────────────────────────────────────────

def export_markdown(result: dict) -> str:
    """Render an investigation result as a Markdown research report."""
    case = result.get("case", {})
    sources = result.get("sources", [])
    stats = result.get("stats", {})
    archive = result.get("archive", {})
    title = case.get("case_title") or "Unidentified Case"

    lines = [f"# Research Hub — {title}", ""]
    lines.append(f"**Confidence:** {case.get('confidence', 'Very Low')}")
    lines.append(f"**Confidence reason:** {case.get('confidence_reason', '')}")
    if case.get("fallback"):
        lines.append("_This is a cautious search target, not a confirmed case identification._")
    lines.append("")

    if case.get("aliases"):
        lines.append("## Aliases")
        lines.extend(f"- {a}" for a in case["aliases"])
        lines.append("")
    if case.get("timeline"):
        lines.append("## Timeline")
        lines.extend(f"- {t}" for t in case["timeline"])
        lines.append("")
    if case.get("victims"):
        lines.append("## Victims")
        lines.extend(f"- {v}" for v in case["victims"])
        lines.append("")
    if case.get("suspects"):
        lines.append("## Suspects")
        lines.extend(f"- {s}" for s in case["suspects"])
        lines.append("")
    if case.get("outcome"):
        lines.append("## Outcome")
        lines.append(case["outcome"])
        lines.append("")

    lines.append("## Sources")
    lines.append("")
    groups = [
        ("Official", "Official Sources"),
        ("Agency", "Official Sources"),
        ("Reporting", "Reporting"),
        ("Investigative", "Reporting"),
    ]
    grouped = {"Official Sources": [], "Reporting": [], "Blocked / Inaccessible": []}
    for src in sources:
        if src.get("tier") == "Wikipedia":
            continue
        if src.get("blocked"):
            grouped["Blocked / Inaccessible"].append(src)
            continue
        label = dict(groups).get(src.get("kind"), "Reporting")
        grouped[label].append(src)

    for label in ("Official Sources", "Reporting"):
        items = grouped[label]
        if not items:
            continue
        lines.append(f"### {label}")
        for src in items:
            lines.append(f"- [{src.get('title', src['url'])}]({src['url']}) — {src.get('kind', '')}")
        lines.append("")

    blocked = grouped["Blocked / Inaccessible"]
    if blocked:
        archived = [s for s in blocked if s.get("archived")]
        not_archived = [s for s in blocked if not s.get("archived")]
        if archived:
            lines.append("### Reporting (Archived)")
            for src in archived:
                lines.append(
                    f"- [{src.get('title', src['url'])}]({src['url']}) — "
                    f"archived via {src.get('archive_provider', 'archive')}: {src.get('archive_url', '')}"
                )
            lines.append("")
        if not_archived:
            lines.append("### Blocked / Inaccessible")
            for src in not_archived:
                lines.append(f"- [{src.get('title', src['url'])}]({src['url']}) — {src.get('inaccessible_reason', 'Inaccessible')}")
            lines.append("")

    lines.append("## Investigation stats")
    lines.append(f"- Elapsed: {result.get('elapsed_seconds', 0)}s")
    lines.append(f"- Sources checked: {stats.get('sources_checked', 0)}")
    lines.append(f"- Slow/blocked sources skipped: {stats.get('skipped_slow_or_blocked', 0)}")
    if stats.get("stopped_reason"):
        lines.append(f"- Stopped because: {stats['stopped_reason']}")
    if archive.get("attempted"):
        lines.append(f"- Archive lookups: {archive['recovered']}/{archive['attempted']} recovered")

    return "\n".join(lines)
