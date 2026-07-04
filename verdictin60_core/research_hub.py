"""Research Hub helpers: multi-clue investigation orchestration for the
Research Hub tab (verdictin60_ui/research_tab.py).

- parse_investigation_input: split a free-text/URL blob into individual
  platform-tagged links and free-text clues.
- identify_case: ask the local AI to identify the most likely case from raw
  input, never inventing facts, with an explicit confidence score.
- check_wayback_availability: query the Internet Archive's free Availability
  API for an archived snapshot of a URL.
- manual_archive_links: build manual-assist lookup links for archive services
  without a stable, scrape-safe API (Archive.today, Memento, CachedView).
- group_sources / run_investigation: orchestrate identification, source
  gathering (via verdictin60_core.research), archive recovery, and confidence
  scoring into one result dict for the UI.
- build_research_caption: generate a caption grounded only in verified
  research sources (no source video required).
"""
import json
import re
import ssl
import urllib.parse
import urllib.request

from verdictin60_core.ai import ollama_identify, ollama_generate
from verdictin60_core.research import (
    fetch_wikipedia_summary, gather_verification_sources, verification_confidence,
    build_verified_fact_sheet, source_section_for_caption,
)

try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except Exception:
    _SSL_CTX = None

_URL_RE = re.compile(r'https?://\S+')

_PLATFORM_MARKERS = (
    ("instagram.com", "Instagram"),
    ("tiktok.com", "TikTok"),
    ("youtube.com", "YouTube"),
    ("youtu.be", "YouTube"),
    ("twitter.com", "X (Twitter)"),
    ("x.com", "X (Twitter)"),
    ("facebook.com", "Facebook"),
    ("reddit.com", "Reddit"),
)


def _detect_platform(url: str) -> str:
    low = url.lower()
    for marker, label in _PLATFORM_MARKERS:
        if marker in low:
            return label
    return "Website"


def parse_investigation_input(raw_text: str) -> dict:
    """Split pasted input into links (with detected platform) and free-text clues.

    Supports pasting multiple lines, multiple URLs, or a single free-text
    paragraph — any combination in one box.
    """
    text = (raw_text or "").strip()
    urls, seen = [], set()
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip('.,;)"\'')
        if url in seen:
            continue
        seen.add(url)
        urls.append({"url": url, "platform": _detect_platform(url)})
    remainder = _URL_RE.sub(" ", text)
    clues = [line.strip() for line in remainder.splitlines() if line.strip()]
    return {"raw_text": text, "urls": urls, "clues": clues}


_IDENTIFY_PROMPT = """You are a case-research assistant for a true-crime archive app.
Given the clues below (names, locations, dates, URLs, keywords, free text), identify the
single most likely real case being described.

Rules:
- Never invent facts. Only state what is reasonably supported by the clues themselves.
- If the clues are too vague or contradictory to identify one specific case, leave
  case_title empty rather than guessing.
- confidence must be exactly one of: High, Medium, Low, Very Low.
- Respond with ONLY a JSON object, no other text, in exactly this shape:
{{
  "case_title": "",
  "aliases": [],
  "confidence": "",
  "reasoning": "",
  "related_people": [],
  "victims": [],
  "suspects": [],
  "outcome": "",
  "timeline": []
}}

Clues:
{clues}
"""

_EMPTY_CASE = {
    "case_title": "", "aliases": [], "confidence": "None",
    "reasoning": "Local AI did not return an identification.",
    "related_people": [], "victims": [], "suspects": [], "outcome": "",
    "timeline": [],
}


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?', '', text).strip()
    text = re.sub(r'```$', '', text).strip()
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def identify_case(raw_text: str) -> dict:
    """Ask the local AI to identify the case described by the raw input.

    Returns case_title/aliases/confidence/reasoning/related_people/victims/
    suspects/outcome/timeline. confidence is "None" and case_title is "" when
    identification fails, times out, or the model can't be reached — the app
    must clearly state when it cannot identify a case rather than guessing.
    """
    empty = dict(_EMPTY_CASE)
    clues = (raw_text or "").strip()
    if not clues:
        empty["reasoning"] = "No input was provided."
        return empty
    try:
        response = ollama_identify(_IDENTIFY_PROMPT.format(clues=clues[:3000]), timeout=45)
    except Exception as e:
        empty["reasoning"] = f"Local AI request failed: {e}"
        return empty
    data = _extract_json(response)
    if not data or not str(data.get("case_title", "")).strip():
        empty["reasoning"] = data.get("reasoning") or "Not enough information to identify a specific case."
        empty["confidence"] = data.get("confidence") or "Very Low"
        return empty
    for key, default in _EMPTY_CASE.items():
        data.setdefault(key, default)
    return data


def _http_get_json(url: str, timeout: int = 10) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VerdictIn60/1.0"})
        kw = {"context": _SSL_CTX} if _SSL_CTX else {}
        with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def check_wayback_availability(url: str) -> dict:
    """Query the Internet Archive's free Availability API for a snapshot of `url`.

    This is the one archive service with a stable, scrape-free JSON API, so
    it's the only one the app checks automatically. Returns
    {"available": bool, "archive_url": str, "timestamp": str}.
    """
    result = {"available": False, "archive_url": "", "timestamp": ""}
    api_url = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    data = _http_get_json(api_url, timeout=10)
    snapshot = data.get("archived_snapshots", {}).get("closest", {})
    if snapshot.get("available") and snapshot.get("url"):
        result["available"] = True
        result["archive_url"] = snapshot["url"]
        result["timestamp"] = snapshot.get("timestamp", "")
    return result


def manual_archive_links(url: str) -> dict:
    """Build manual-assist lookup links for archive services without a free,
    scrape-safe API. The app does not auto-fetch these — it hands the user a
    direct link to check itself, and labels them clearly as manual lookups."""
    return {
        "Archive.today": f"https://archive.ph/{url}",
        "Memento Time Travel": f"https://timetravel.mementoweb.org/timemap/link/{url}",
        "CachedView": "https://cachedview.nl/",
    }


def recover_source_archive(source: dict) -> dict:
    """Attach archive-recovery info to a blocked/inaccessible source.

    Tries the Wayback Machine automatically; if no snapshot is available,
    attaches manual lookup links for the other archive services instead of
    guessing that a snapshot exists.
    """
    wayback = check_wayback_availability(source.get("url", ""))
    if wayback["available"]:
        source["archived"] = True
        source["archive_provider"] = "Wayback Machine"
        source["archive_url"] = wayback["archive_url"]
    else:
        source["archived"] = False
        source["manual_archive_links"] = manual_archive_links(source.get("url", ""))
    return source


def group_sources(sources: list) -> dict:
    """Group gathered sources into the 4 Research Hub result buckets."""
    official, reporting_accessible, reporting_archived, blocked = [], [], [], []
    for src in sources:
        if src.get("tier") == "Wikipedia":
            continue
        if src.get("blocked"):
            recovered = recover_source_archive(src)
            if recovered.get("archived"):
                reporting_archived.append(recovered)
            else:
                blocked.append(recovered)
        elif src.get("kind") == "Official":
            official.append(src)
        else:
            reporting_accessible.append(src)
    return {
        "official": official,
        "reporting_accessible": reporting_accessible,
        "reporting_archived": reporting_archived,
        "blocked": blocked,
    }


def run_investigation(raw_text: str, progress_cb=None) -> dict:
    """Run the full Research Hub investigation pipeline.

    progress_cb, if given, is called with short human-readable status strings
    so a UI can show progress while this runs on a background thread.
    """
    def _progress(msg):
        if progress_cb:
            progress_cb(msg)

    parsed = parse_investigation_input(raw_text)
    _progress("Identifying the most likely case…")
    case = identify_case(raw_text)

    result = {
        "input": parsed,
        "case": case,
        "wiki_title": "",
        "sources": {"official": [], "reporting_accessible": [], "reporting_archived": [], "blocked": []},
        "all_sources": [],
        "confidence_label": "Very low",
        "confidence_reason": "No case could be identified from the input.",
    }

    case_title = str(case.get("case_title", "")).strip()
    if not case_title:
        return result

    _progress(f"Researching {case_title}…")
    wiki_facts, wiki_title = fetch_wikipedia_summary(case_title)
    result["wiki_title"] = wiki_title

    _progress("Gathering official, legal, and reporting sources…")
    sources = gather_verification_sources(case_title, raw_text, wiki_title, wiki_facts)

    _progress("Checking archive recovery for inaccessible sources…")
    grouped = group_sources(sources)
    label, reason = verification_confidence(sources)

    result["sources"] = grouped
    result["all_sources"] = sources
    result["confidence_label"] = label
    result["confidence_reason"] = reason
    return result


def build_research_caption(case_title: str, sources: list) -> str:
    """Generate a caption grounded only in verified research (no source video).

    Reuses the same verified-fact-sheet approach as the main caption pipeline
    so the Research Hub never invents details beyond what sources support.
    """
    fact_sheet = build_verified_fact_sheet(case_title, sources)
    prompt = (
        "Write a short, factual true-crime caption (5-8 sentences) for the case below, "
        "using ONLY the verified facts provided. Do not invent names, dates, locations, "
        "or outcomes that are not explicitly present. If a detail is not verified, omit "
        "it rather than guessing.\n\n" + fact_sheet
    )
    try:
        caption = ollama_generate(prompt, task="caption", num_predict=500).strip()
    except Exception:
        caption = ""
    if not caption:
        caption = (
            f"{case_title}\n\nInsufficient verified detail was available to "
            "auto-generate a caption. Review the sources below manually."
        )
    return caption + "\n\n" + source_section_for_caption(sources)
