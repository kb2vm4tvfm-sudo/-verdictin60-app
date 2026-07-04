"""Research Hub orchestration.

- parse_investigation_input: split a free-form paste (names, dates, keywords,
  one or many platform/website URLs) into structured clues.
- identify_case: ask the local AI to identify the most likely real case from
  those clues, with an explicit confidence score and reasoning. Never invents
  facts — says so plainly when confidence is too low.
- wayback_lookup / manual_archive_links / recover_blocked_sources: archive
  recovery for sources research.gather_verification_sources() could not reach.
- investigate: end-to-end orchestration — identify, gather sources under a
  strict time/source budget (verdictin60_core.research's fixes), recover
  archives for blocked sources, and return a single result dict.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from verdictin60_core import research
from verdictin60_core.ai import ollama_identify

INVESTIGATION_DEADLINE_SECONDS = research.DEFAULT_INVESTIGATION_DEADLINE
MAX_SOURCES_CHECKED = research.DEFAULT_MAX_SOURCES_CHECKED

_URL_PATTERN = re.compile(r'https?://\S+')

_PLATFORM_HOSTS = (
    ("instagram.com", "Instagram"),
    ("tiktok.com", "TikTok"),
    ("youtube.com", "YouTube"),
    ("youtu.be", "YouTube"),
    ("twitter.com", "X (Twitter)"),
    ("x.com", "X (Twitter)"),
    ("facebook.com", "Facebook"),
    ("reddit.com", "Reddit"),
)


def _platform_for_url(url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    for host, label in _PLATFORM_HOSTS:
        if domain == host or domain.endswith("." + host):
            return label
    return "Web"


def parse_investigation_input(raw_text: str) -> dict:
    """Split a free-form paste into structured clues (URLs by platform, plain
    text lines/keywords, and any years mentioned). Pure pattern matching —
    does not guess at meaning beyond that."""
    raw_text = (raw_text or "").strip()
    urls = []
    for m in _URL_PATTERN.finditer(raw_text):
        url = m.group(0).rstrip(').,;\'"')
        urls.append({"url": url, "platform": _platform_for_url(url)})
    text_without_urls = _URL_PATTERN.sub(" ", raw_text)
    lines = [ln.strip() for ln in text_without_urls.splitlines() if ln.strip()]
    years = sorted(set(re.findall(r"\b(?:18|19|20)\d{2}\b", raw_text)))
    return {
        "raw_text": raw_text,
        "urls": urls,
        "text_lines": lines,
        "keywords": lines,
        "years": years,
    }


def _strip_ai_json(raw: str) -> dict:
    text = re.sub(r'<think>.*?</think>', '', raw or "", flags=re.DOTALL | re.IGNORECASE).strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def identify_case(clues: dict) -> dict:
    """Ask the local AI to identify the most likely case from the clues.

    Returns {"identified": False, ...} (with a plain-language reasoning
    string) whenever the AI is unavailable, its response can't be parsed, or
    it says the clues are too vague — this function never fabricates a case.
    """
    clue_text = clues.get("raw_text", "")[:2500]
    url_lines = "\n".join(f"- {u['platform']}: {u['url']}" for u in clues.get("urls", []))
    prompt = f"""You are a case-identification assistant for a true-crime research tool.
You are given raw clues a researcher pasted in — names, locations, dates, keywords, or links.

Clues:
{clue_text}

Links found:
{url_lines or "(none)"}

Identify the most likely real case these clues refer to. Rules:
- NEVER invent facts, names, dates, or outcomes. Only state what you can reasonably infer from the clues themselves.
- If the clues are too vague or generic to identify a specific real case, say so explicitly instead of guessing.
- List any aliases, nicknames, or alternate spellings you recognize for the people involved, only if you are confident.
- Give a confidence level: High, Medium, Low, or Very Low.
- Briefly explain your reasoning.

Respond ONLY with JSON in exactly this shape:
{{
  "identified": true or false,
  "case_title": "string, best-guess public case name, or empty string",
  "aliases": ["list of known aliases/nicknames, or empty list"],
  "confidence": "High" | "Medium" | "Low" | "Very Low",
  "reasoning": "one or two sentences explaining the identification",
  "related_people": ["names mentioned or clearly implied by the clues"]
}}"""
    try:
        raw = ollama_identify(prompt)
    except Exception as e:
        print(f"[RESEARCH_HUB] identify_case: AI unavailable ({e})")
        return {
            "identified": False, "case_title": "", "aliases": [],
            "confidence": "Very Low",
            "reasoning": "The local AI model was unavailable, so no case could be identified.",
            "related_people": [],
        }

    data = _strip_ai_json(raw)
    if not data:
        return {
            "identified": False, "case_title": "", "aliases": [],
            "confidence": "Very Low",
            "reasoning": "The AI response could not be parsed into a case identification.",
            "related_people": [],
        }
    data.setdefault("identified", bool(data.get("case_title")))
    data.setdefault("case_title", "")
    data.setdefault("aliases", [])
    data.setdefault("confidence", "Very Low")
    data.setdefault("reasoning", "")
    data.setdefault("related_people", [])
    if not data.get("case_title"):
        data["identified"] = False
    return data


# ── Archive recovery ────────────────────────────────────────────────────────

def wayback_lookup(url: str, timeout: int = 6) -> dict:
    """Check the Internet Archive's free Wayback Availability API for an
    archived snapshot of `url`. Never raises — returns {"available": False}
    on any failure."""
    try:
        api_url = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
        req = urllib.request.Request(api_url, headers={"User-Agent": "VerdictIn60/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available"):
            return {
                "available": True,
                "archive_url": snapshot.get("url", "").replace(
                    "http://web.archive.org", "https://web.archive.org"
                ),
                "timestamp": snapshot.get("timestamp", ""),
            }
    except Exception as e:
        print(f"[RESEARCH_HUB] Wayback lookup failed for {url[:90]}: {e}")
    return {"available": False, "archive_url": "", "timestamp": ""}


def manual_archive_links(url: str) -> dict:
    """Archive.today/Memento/CachedView have no stable, scrape-safe public
    API — surface manual lookup links for these instead of guessing results."""
    return {
        "archive_today": f"https://archive.ph/{url}",
        "memento": f"https://timetravel.mementoweb.org/timemap/link/{url}",
        "cached_view": "https://cachedview.nl/",
    }


def recover_blocked_sources(sources: list, deadline_seconds: float = 20) -> list:
    """For each blocked/inaccessible source, try the Wayback Machine first;
    otherwise attach manual lookup links for the other archive services.
    Recovered pages are always labeled with their archive provider — never
    presented as if they were the live source."""
    start = time.time()
    for src in sources:
        if not src.get("blocked"):
            continue
        if time.time() - start >= deadline_seconds:
            src["archive"] = {"checked": False, "reason": "archive recovery time budget reached"}
            continue
        result = wayback_lookup(src["url"])
        if result["available"]:
            src["archive"] = {
                "checked": True,
                "provider": "Wayback Machine",
                "archive_url": result["archive_url"],
                "timestamp": result["timestamp"],
            }
        else:
            src["archive"] = {
                "checked": True,
                "provider": None,
                "manual_links": manual_archive_links(src["url"]),
            }
    return sources


# ── Investigation orchestration ──────────────────────────────────────────────

def investigate(raw_text: str,
                deadline_seconds: float = None,
                max_sources: int = None,
                archive_deadline_seconds: float = 20) -> dict:
    """Run a full Research Hub investigation from free-form pasted clues.

    Enforces the overall time/source budget requested for the Research Hub
    (default ~75s / 20 sources) so a single investigation stays in the
    60-90 second range instead of running for minutes. Returns:
      {
        "clues": parse_investigation_input() output,
        "case": identify_case() output,
        "confidence_label": "High"|"Medium"|"Low"|"Very low",
        "confidence_reason": str,
        "sources": [...research.gather_verification_sources() results,
                     each annotated with "archive" if blocked...],
        "stats": {"elapsed_seconds", "sources_checked", "stopped_reason",
                   "skipped_slow_or_blocked", "total_elapsed_seconds"},
      }
    """
    deadline_seconds = deadline_seconds or research.DEFAULT_INVESTIGATION_DEADLINE
    max_sources = max_sources or research.DEFAULT_MAX_SOURCES_CHECKED
    started = time.time()

    clues = parse_investigation_input(raw_text)
    case = identify_case(clues)

    if not case.get("identified") or not case.get("case_title"):
        return {
            "clues": clues,
            "case": case,
            "confidence_label": "Very low",
            "confidence_reason": "Confidence was too low to identify a specific case from the clues provided.",
            "sources": [],
            "stats": {
                "elapsed_seconds": 0,
                "sources_checked": 0,
                "stopped_reason": "case not identified",
                "skipped_slow_or_blocked": [],
                "total_elapsed_seconds": round(time.time() - started, 1),
            },
        }

    case_title = case["case_title"]
    wiki_facts, wiki_title = research.fetch_wikipedia_summary(case_title)

    remaining = max(5.0, deadline_seconds - (time.time() - started))
    stats: dict = {}
    sources = research.gather_verification_sources(
        case_title, clues.get("raw_text", ""),
        wiki_title=wiki_title, wiki_facts=wiki_facts,
        deadline_seconds=remaining, max_sources=max_sources, stats=stats,
    )

    archive_budget = max(5.0, min(archive_deadline_seconds, deadline_seconds - (time.time() - started)))
    sources = recover_blocked_sources(sources, deadline_seconds=archive_budget)

    confidence_label, confidence_reason = research.verification_confidence(sources)
    stats["total_elapsed_seconds"] = round(time.time() - started, 1)

    return {
        "clues": clues,
        "case": case,
        "confidence_label": confidence_label,
        "confidence_reason": confidence_reason,
        "sources": sources,
        "stats": stats,
    }
