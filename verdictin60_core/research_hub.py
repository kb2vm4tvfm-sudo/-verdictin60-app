"""Research Hub orchestration: multi-clue parsing, AI case identification,
archive recovery, and investigation orchestration on top of the existing
verification pipeline in verdictin60_core/research.py.

- parse_clues: split free-form pasted text (names, URLs, keywords, one per
  line or comma-separated) into structured clue data.
- identify_case: ask the local AI model to identify the most likely real
  case from the clues — never inventing facts, and stating plainly when
  confidence is too low to identify a case.
- check_wayback_availability / recover_archives: Wayback Machine archive
  recovery for sources gather_verification_sources marked inaccessible.
- investigate: run identification + budgeted source gathering + archive
  recovery and return a single result dict for the Research Hub UI.
- group_sources_for_display: bucket sources into Official / Reporting
  (Accessible) / Reporting (Archived) / Blocked for the results view.
- generate_caption: build a VerdictIn60 caption grounded only in the
  sources an investigation found.
- export_markdown: render an investigation result as a Markdown report.
"""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request

from verdictin60_core.ai import ollama_generate, ollama_identify
from verdictin60_core.captions import caption_needs_fallback
from verdictin60_core.research import (
    build_verified_fact_sheet,
    fetch_wikipedia_summary,
    format_blocked_sources_for_prompt,
    format_sources_for_prompt,
    gather_verification_sources,
    source_section_for_caption,
    verification_confidence,
)

# Investigation budget defaults — keeps a full Research Hub pass in the
# 60-90s range instead of the 5+ minutes reported before research.py's
# per-URL timeouts/budgets were added.
DEFAULT_DEADLINE_SECONDS = 75
DEFAULT_MAX_SOURCES = 20

DEFAULT_HASHTAGS = (
    "#truecrime #verdictin60 #truecrimecommunity #coldcase #justice "
    "#realcrimecases #crimeawareness #crimearchive #truecrimestories "
    "#crimeanalysis #lawandcrime #casefile #truecrimeobsessed #victimsmatter "
    "#crimebreakdown #truecrimefacts #truestoryreels #crimecommunity "
    "#crimehistory #investigation #coldcasefiles"
)

_URL_RE = re.compile(r"https?://\S+", re.I)


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


# ── Clue parsing ────────────────────────────────────────────────────────────

def parse_clues(raw_text: str) -> dict:
    """Split free-form pasted clue text into URLs and text fragments.

    Accepts one clue per line, comma-separated clues, platform URLs, or a
    mix of prose and links — exactly what the Research Hub search panel
    accepts (names, locations, dates, keywords, case numbers, or any URL).
    """
    raw_text = (raw_text or "").strip()
    urls = []
    for m in _URL_RE.finditer(raw_text):
        u = m.group(0).rstrip(").,;”’'\"")
        if u not in urls:
            urls.append(u)

    text_without_urls = _URL_RE.sub(" ", raw_text)
    fragments = []
    for line in text_without_urls.splitlines():
        for frag in line.split(","):
            frag = frag.strip(" -*•\t")
            if frag and frag not in fragments:
                fragments.append(frag)

    return {"raw_text": raw_text, "urls": urls, "fragments": fragments}


# ── AI case identification ──────────────────────────────────────────────────

def _as_str_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _extract_json_object(raw: str) -> dict:
    if not raw:
        return {}
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _unidentified_case(reason: str) -> dict:
    return {
        "identified": False,
        "case_title": "",
        "aliases": [],
        "confidence": "Very low",
        "confidence_reason": reason,
        "reasoning": "",
        "victims": [],
        "suspects": [],
        "related_people": [],
        "timeline": [],
        "outcome": "",
    }


def identify_case(clues: dict) -> dict:
    """Ask the local AI model to identify the most likely real case from the
    given clues. Never invents facts: the prompt requires the model to leave
    fields empty and set confidence to "Very low" when it isn't sure, and
    `identified` is only True when the model both named a case and expressed
    at least Low confidence in it.
    """
    clue_text = (clues or {}).get("raw_text", "").strip()
    if not clue_text:
        return _unidentified_case("No clues were provided.")

    prompt = (
        "You are a cautious true-crime research assistant helping identify a "
        "real criminal case from partial clues (names, locations, dates, "
        "URLs, keywords, headlines). You must NEVER invent facts, names, "
        "dates, or outcomes that are not directly supported by the clues "
        "below. If you cannot identify a specific real case with reasonable "
        "confidence, say so plainly and set confidence to \"Very low\" with "
        "an empty case_title.\n\n"
        "Clues:\n"
        f"{clue_text[:3000]}\n\n"
        "Respond with ONLY a single JSON object (no prose, no markdown "
        "fences) using exactly this shape:\n"
        "{\n"
        '  "case_title": "Most likely real case name, or empty string if unidentified",\n'
        '  "aliases": ["alternate spellings, nicknames, or aliases"],\n'
        '  "confidence": "High" | "Medium" | "Low" | "Very low",\n'
        '  "confidence_reason": "one sentence explaining the confidence level",\n'
        '  "reasoning": "1-3 sentences on why this case matches the clues",\n'
        '  "victims": ["victim names, only if supported by the clues"],\n'
        '  "suspects": ["suspect/defendant names, only if supported"],\n'
        '  "related_people": ["other named people relevant to the case"],\n'
        '  "timeline": ["short chronological event strings, only if supported"],\n'
        '  "outcome": "legal outcome if known, else empty string"\n'
        "}\n"
    )
    try:
        raw = ollama_identify(prompt)
    except Exception as e:
        print(f"[{_ts()} RESEARCH_HUB] identify_case AI call failed: {e}")
        return _unidentified_case("The local AI model was not reachable.")

    data = _extract_json_object(raw)
    if not data:
        return _unidentified_case(
            "The AI could not produce a usable identification from these clues."
        )

    case_title = str(data.get("case_title") or "").strip()
    confidence = str(data.get("confidence") or "Very low").strip().title()
    if confidence not in ("High", "Medium", "Low", "Very Low"):
        confidence = "Very Low"
    confidence = "Very low" if confidence == "Very Low" else confidence

    return {
        "identified": bool(case_title) and confidence != "Very low",
        "case_title": case_title,
        "aliases": _as_str_list(data.get("aliases")),
        "confidence": confidence,
        "confidence_reason": str(data.get("confidence_reason") or "").strip(),
        "reasoning": str(data.get("reasoning") or "").strip(),
        "victims": _as_str_list(data.get("victims")),
        "suspects": _as_str_list(data.get("suspects")),
        "related_people": _as_str_list(data.get("related_people")),
        "timeline": _as_str_list(data.get("timeline")),
        "outcome": str(data.get("outcome") or "").strip(),
    }


# ── Archive recovery ─────────────────────────────────────────────────────────

def check_wayback_availability(url: str, timeout: int = 8) -> dict:
    """Query the Internet Archive's free Wayback Availability API for a
    snapshot of `url`. Returns {} if no snapshot is available or the request
    failed — never guesses a URL that wasn't confirmed by the API."""
    try:
        api_url = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
        req = urllib.request.Request(api_url, headers={"User-Agent": "VerdictIn60/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        snap = (data.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available") and snap.get("url"):
            return {
                "provider": "Wayback Machine",
                "archive_url": snap["url"].replace("http://web.archive.org", "https://web.archive.org"),
                "archived_at": snap.get("timestamp", ""),
            }
    except Exception as e:
        print(f"[{_ts()} RESEARCH_HUB] Wayback lookup failed for {url[:80]}: {e}")
    return {}


def _manual_archive_links(url: str) -> list:
    """Archive.today, Memento Time Travel, and CachedView don't offer a
    stable, scrape-safe lookup API — surface direct manual-lookup links for
    the user instead of guessing whether a snapshot exists."""
    return [
        {"provider": "Archive.today", "url": f"https://archive.ph/{url}"},
        {"provider": "Memento Time Travel", "url": f"http://timetravel.mementoweb.org/timemap/link/{url}"},
        {"provider": "CachedView", "url": "https://cachedview.nl/"},
    ]


def recover_archives(sources: list, deadline_seconds: float = None, max_lookups: int = 12) -> None:
    """Mutate `sources` in place: attempt a Wayback Machine lookup for every
    blocked source and attach manual lookup links for the other archive
    services. Recovered pages are marked archived_accessible=True so the UI
    can label them clearly as archived rather than live sources.

    Bounded by `deadline_seconds` (wall-clock) and `max_lookups` (Wayback API
    calls) so a case with many blocked sources can't blow past the Research
    Hub's total investigation time budget — once either limit is hit, the
    remaining blocked sources just get manual lookup links instead.
    """
    start = time.time()
    lookups_done = 0
    for src in sources:
        if not src.get("blocked"):
            continue
        out_of_budget = (
            lookups_done >= max_lookups
            or (deadline_seconds is not None and (time.time() - start) >= deadline_seconds)
        )
        if out_of_budget:
            src["archive"] = {"manual_links": _manual_archive_links(src["url"])}
            src["archived_accessible"] = False
            continue
        lookups_done += 1
        wb = check_wayback_availability(src["url"])
        if wb:
            src["archive"] = wb
            src["archived_accessible"] = True
        else:
            src["archive"] = {"manual_links": _manual_archive_links(src["url"])}
            src["archived_accessible"] = False


# ── Investigation orchestration ─────────────────────────────────────────────

def investigate(raw_clues: str, deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
                max_sources: int = DEFAULT_MAX_SOURCES) -> dict:
    """Run a full Research Hub investigation: identify the case, gather
    sources under the given time/source budget, and recover archives for
    blocked sources. Returns a result dict ready for the UI and actions.
    """
    t_start = time.time()
    clues = parse_clues(raw_clues)
    case = identify_case(clues)

    result = {
        "clues": clues,
        "case": case,
        "sources": [],
        "stats": {},
        "wiki_title": "",
        "research_confidence": "Very low",
        "research_confidence_reason": "No case was identified from these clues.",
        "elapsed_seconds": 0.0,
    }

    if not case.get("case_title"):
        result["elapsed_seconds"] = round(time.time() - t_start, 1)
        return result

    case_title = case["case_title"]
    wiki_facts, wiki_title = fetch_wikipedia_summary(case_title)
    result["wiki_title"] = wiki_title

    context_text = " ".join(filter(None, [
        clues.get("raw_text", ""),
        case.get("reasoning", ""),
        " ".join(case.get("timeline", [])),
    ]))[:1800]

    stats = {}
    remaining = max(5.0, deadline_seconds - (time.time() - t_start))
    sources = gather_verification_sources(
        case_title, context_text, wiki_title, wiki_facts,
        deadline_seconds=remaining, max_sources=max_sources, stats=stats,
    )
    # Archive recovery gets a slice of whatever's left of the total budget so
    # a case with many blocked sources can't push the investigation well past
    # the 60-90s target — anything past this uses manual lookup links instead.
    archive_deadline = max(10.0, deadline_seconds - (time.time() - t_start))
    recover_archives(sources, deadline_seconds=archive_deadline)

    confidence_label, confidence_reason = verification_confidence(sources)

    result["sources"] = sources
    result["stats"] = stats
    result["research_confidence"] = confidence_label
    result["research_confidence_reason"] = confidence_reason
    result["elapsed_seconds"] = round(time.time() - t_start, 1)
    return result


def group_sources_for_display(sources: list) -> dict:
    """Bucket gathered + archive-recovered sources into the four groups the
    Research Hub results view displays: Official, Reporting (Accessible),
    Reporting (Archived), and Blocked/Inaccessible."""
    groups = {"official": [], "reporting_accessible": [], "reporting_archived": [], "blocked": []}
    for src in sources:
        if src.get("tier") == "Wikipedia":
            continue
        kind = src.get("kind", "Reference")
        if not src.get("blocked"):
            if kind in ("Official", "Agency"):
                groups["official"].append(src)
            else:
                groups["reporting_accessible"].append(src)
        elif src.get("archived_accessible"):
            groups["reporting_archived"].append(src)
        else:
            groups["blocked"].append(src)
    return groups


# ── Caption generation ───────────────────────────────────────────────────────

def _fallback_caption(case_title: str, confidence: str, confidence_reason: str,
                      source_section: str) -> str:
    body = (
        f"VerdictIn60: {case_title}\n\n"
        f"This case is under review. Verification confidence: {confidence} "
        f"({confidence_reason or 'limited accessible source material'}).\n\n"
        "The sources gathered so far were not sufficient to generate a fully "
        "detailed caption automatically — review the sources in this "
        "investigation before publishing."
    )
    return (
        f"{body}\n\n{source_section}\n\n"
        "Follow @VerdictIn60 for daily true crime.\n\n"
        f"{DEFAULT_HASHTAGS}"
    )


def generate_caption(case: dict, sources: list) -> str:
    """Generate a VerdictIn60-style caption grounded only in the verified
    sources an investigation found. Falls back to a plain, cautious caption
    if the local AI is unavailable or its output fails validation."""
    case_title = case.get("case_title") or "Unidentified case"
    confidence = case.get("confidence", "Very low")
    confidence_reason = case.get("confidence_reason", "")
    source_prompt_text = format_sources_for_prompt(sources)
    blocked_prompt_text = format_blocked_sources_for_prompt(sources)
    verified_fact_sheet = build_verified_fact_sheet(case_title, sources)
    source_section = source_section_for_caption(sources)

    prompt = (
        "You are writing a VerdictIn60 Instagram caption for a case "
        "researched through the Research Hub.\n\n"
        f"Case: {case_title}\n"
        f"Verification confidence: {confidence} — {confidence_reason}\n\n"
        "Use only the verified fact sheet and accessible sources below. Do "
        "not invent names, dates, motives, quotes, locations, charges, "
        "sentences, or emotional details. If a detail is not supported, "
        "omit it or phrase cautiously.\n\n"
        "Verified fact sheet:\n"
        f"{verified_fact_sheet}\n\n"
        "Accessible sources:\n"
        f"{source_prompt_text[:6500]}\n\n"
        "Blocked but discovered sources:\n"
        f"{blocked_prompt_text[:1800]}\n\n"
        "Requirements:\n"
        "- Strong hook, short dramatic paragraphs, chronological storytelling.\n"
        "- Clear respectful tone; no unsupported dramatic claims.\n"
        "- Add one engagement question near the end.\n"
        "- Include: Follow @VerdictIn60 for daily true crime.\n"
        "- End with this exact Research & Verification section:\n"
        f"{source_section}\n"
        "- Include exactly 20 relevant hashtags at the end.\n"
        "- Do not list Wikipedia in Research & Verification.\n"
        "- End the entire answer with END_OF_CAPTION.\n"
        "- Return only the caption."
    )
    try:
        raw = ollama_generate(prompt, task="caption")
    except Exception as e:
        print(f"[{_ts()} RESEARCH_HUB] caption generation failed: {e}")
        raw = ""

    caption = raw.split("END_OF_CAPTION")[0].strip() if raw else ""
    fallback_reason = caption_needs_fallback(caption) if caption else "empty"
    if fallback_reason:
        print(f"[{_ts()} RESEARCH_HUB] AI caption fallback ({fallback_reason}) — using cautious template")
        return _fallback_caption(case_title, confidence, confidence_reason, source_section)
    return caption


# ── Markdown export ──────────────────────────────────────────────────────────

def export_markdown(result: dict) -> str:
    """Render a full investigation result dict as a Markdown report."""
    case = result.get("case", {})
    case_title = case.get("case_title") or "Unidentified case"
    lines = [f"# {case_title}", ""]

    lines.append(f"**Confidence:** {case.get('confidence', 'Very low')}")
    if case.get("confidence_reason"):
        lines.append(f"**Confidence reason:** {case['confidence_reason']}")
    if case.get("aliases"):
        lines.append(f"**Aliases:** {', '.join(case['aliases'])}")
    lines.append("")

    if case.get("reasoning"):
        lines += ["## Why this case", case["reasoning"], ""]

    if case.get("timeline"):
        lines.append("## Timeline")
        lines += [f"- {event}" for event in case["timeline"]]
        lines.append("")

    if case.get("victims"):
        lines += ["## Victims", ", ".join(case["victims"]), ""]
    if case.get("suspects"):
        lines += ["## Suspects", ", ".join(case["suspects"]), ""]
    if case.get("related_people"):
        lines += ["## Related people", ", ".join(case["related_people"]), ""]
    if case.get("outcome"):
        lines += ["## Outcome", case["outcome"], ""]

    groups = group_sources_for_display(result.get("sources", []))
    section_titles = [
        ("official", "Official Sources"),
        ("reporting_accessible", "Reporting (Accessible)"),
        ("reporting_archived", "Reporting (Archived)"),
        ("blocked", "Blocked / Inaccessible"),
    ]
    lines.append("## Sources")
    for key, title in section_titles:
        items = groups.get(key, [])
        lines.append(f"### {title}")
        if not items:
            lines.append("- None found.")
        for src in items:
            entry = f"- [{src.get('title') or src.get('url')}]({src.get('url', '')})"
            if src.get("archive", {}).get("archive_url"):
                entry += f" — archived: {src['archive']['archive_url']}"
            lines.append(entry)
        lines.append("")

    stats = result.get("stats") or {}
    if stats:
        lines.append("## Investigation stats")
        lines.append(f"- Elapsed: {result.get('elapsed_seconds', stats.get('elapsed_seconds', '?'))}s")
        lines.append(f"- Sources checked: {stats.get('sources_checked', '?')}")
        lines.append(f"- Slow/blocked skipped: {stats.get('skipped_slow_or_blocked', '?')}")
        lines.append(f"- Stopped reason: {stats.get('stopped_reason', '?')}")

    return "\n".join(lines)
