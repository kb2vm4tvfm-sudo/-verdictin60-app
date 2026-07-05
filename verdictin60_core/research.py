"""Source research and verification helpers, moved from app.py (Phase 5 refactor,
no behavior change).

- fetch_wikipedia_summary: Wikipedia orientation lookup (curl-based, with
  richer-article and full-extract fallbacks).
- _strip_html_text / _extract_readable_text / _looks_like_block_page /
  _page_title: HTML-to-text extraction helpers used while reading fetched pages.
- _fetch_url_text / _fetch_raw_url: low-level URL fetch helpers.
- _find_browser_executable / _fetch_playwright_rendered_html /
  _fetch_browser_rendered_html: browser-rendered fallback for pages that block
  plain urllib requests.
- _load_source_cache / _save_source_cache: on-disk cache for web search results.
- _search_web / _ddg_search: multi-engine web search with caching.
- _fetch_wiki_citations: pull citation URLs out of a Wikipedia article's wikitext.
- _search_courtlistener: CourtListener legal-opinion search.
- _classify_source: map a URL/title to a source tier label.
- gather_verification_sources: the 5-tier source-gathering strategy.
- format_sources_for_prompt / format_blocked_sources_for_prompt: format
  gathered sources for the AI caption prompt.
- verification_confidence: derive a confidence label/reason from gathered sources.
- build_verified_fact_sheet: build the verified-fact-sheet prompt block.
- source_section_for_caption: build the public "Research & Verification"
  caption footer.
"""
import datetime
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

SOURCE_CACHE_PATH = Path(__file__).resolve().parent.parent / "source-cache.json"

# ── Fetch timeout / retry budgets ──────────────────────────────────────────────
# Keep these small so a single slow/blocked source can't stall an investigation.
DIRECT_FETCH_TIMEOUT  = 7   # seconds — plain urllib fetch of a source page
BROWSER_FETCH_TIMEOUT = 9   # seconds — single browser-rendered fallback attempt

# Known paywalled domains: browser rendering never gets past their paywall, so
# skip straight to Blocked/Inaccessible (archive recovery can still find them)
# instead of burning a ~9s browser-fallback attempt that will fail anyway.
_PAYWALLED_DOMAINS = (
    "nytimes.com", "wsj.com", "washingtonpost.com", "bloomberg.com", "ft.com",
    "newyorker.com", "wired.com", "economist.com", "theatlantic.com",
    "businessinsider.com", "telegraph.co.uk", "thetimes.co.uk",
)

# Brave search 429 (rate-limit) backoff — module-level so it persists for the
# rest of this process's searches, not just the current investigation.
_BRAVE_BACKOFF_SECONDS = 600
_brave_backoff_until = 0.0


def _brave_in_backoff() -> bool:
    return time.time() < _brave_backoff_until


def _set_brave_backoff():
    global _brave_backoff_until
    _brave_backoff_until = time.time() + _BRAVE_BACKOFF_SECONDS
    print(f"[{_ts()} SOURCES] Brave rate-limited (429) — backing off {_BRAVE_BACKOFF_SECONDS}s")


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def fetch_wikipedia_summary(case_name: str):
    """Fetch Wikipedia article via curl (avoids macOS Python SSL cert issues).
    If the direct page summary is short (<500 chars), searches for a richer article.
    If the best summary is still under 1000 chars, fetches the full article extract.
    Returns (extract_text, page_title). Both are empty strings on failure."""
    import urllib.parse

    def _curl_json(url):
        r = subprocess.run(
            ["curl", "-s", "-A", "VerdictIn60/1.0", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout:
            try:
                return json.loads(r.stdout)
            except Exception:
                pass
        return {}

    def _full_extract(page_title: str) -> str:
        """Fetch full article plaintext via MediaWiki API."""
        enc = urllib.parse.quote(page_title.replace(" ", "_"))
        url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=query&titles={enc}&prop=extracts"
            "&exintro=false&explaintext=true&format=json"
        )
        data = _curl_json(url)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            text = page.get("extract", "")
            if text:
                return text
        return ""

    try:
        search_term = urllib.parse.quote(case_name.replace(" ", "_"))

        # Step 1: direct page lookup
        data    = _curl_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term}")
        extract = data.get("extract", "")
        title   = data.get("title", "")

        # Step 2: if result is thin, search for a better article — but only
        # upgrade if the new page title still refers to the same person/case.
        if len(extract) < 500:
            search_url = (
                "https://en.wikipedia.org/w/api.php"
                f"?action=query&list=search&srsearch={search_term}"
                "&format=json&srlimit=5"
            )
            search_data = _curl_json(search_url)
            hits = search_data.get("query", {}).get("search", [])
            case_words = set(case_name.lower().split())
            for hit in hits:
                candidate_title = hit["title"]
                candidate_words = set(candidate_title.lower().split())
                # Only upgrade if the candidate page title shares meaningful
                # words with the case name (avoids author/documentary redirects)
                if not case_words & candidate_words:
                    print(f"[{_ts()} URL_IMPORT] Wikipedia skipped unrelated: {candidate_title!r}")
                    continue
                page_term = urllib.parse.quote(candidate_title.replace(" ", "_"))
                page_data = _curl_json(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_term}"
                )
                page_extract = page_data.get("extract", "")
                if len(page_extract) > len(extract):
                    extract = page_extract
                    title   = page_data.get("title", title)
                    print(f"[{_ts()} URL_IMPORT] Wikipedia upgraded to: {title!r} ({len(extract)} chars)")
                    break

        # Step 3: if still under 1000 chars, fetch the full article extract
        if title and len(extract) < 1000:
            full = _full_extract(title)
            if len(full) > len(extract):
                extract = full
                print(f"[{_ts()} URL_IMPORT] Wikipedia full article fetched: {title!r} ({len(extract)} chars)")

        if extract:
            print(f"[{_ts()} URL_IMPORT] Wikipedia facts: {title!r} ({len(extract)} chars)")
            return extract, title
    except Exception as e:
        print(f"[{_ts()} URL_IMPORT] Wikipedia lookup failed: {e}")
    return "", ""


def _strip_html_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;|&apos;", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_readable_text(raw_html: str) -> str:
    """Extract article-like text from HTML, falling back to whole-page text."""
    candidates = []
    for pattern in (
        r"(?is)<article\b[^>]*>(.*?)</article>",
        r"(?is)<main\b[^>]*>(.*?)</main>",
        r'(?is)<div\b[^>]+(?:article|story|content|entry|post|body)[^>]*>(.*?)</div>',
    ):
        for m in re.finditer(pattern, raw_html):
            text = _strip_html_text(m.group(1))
            if len(text) > 500:
                candidates.append(text)
    if candidates:
        return max(candidates, key=len)
    return _strip_html_text(raw_html)


def _looks_like_block_page(text: str) -> bool:
    hay = text[:2500].lower()
    markers = (
        "enable javascript", "verify you are human", "checking your browser",
        "access denied", "403 forbidden", "are you a robot", "captcha",
        "cloudflare", "please disable your ad blocker", "subscribe to continue",
        "sign in to continue", "consent.google.com",
    )
    return any(m in hay for m in markers)


def _fetch_url_text(url: str, timeout: int = 10) -> str:
    raw = _fetch_raw_url(url, timeout=timeout)
    if not raw:
        return ""
    return _extract_readable_text(raw)[:5000]


def _page_title(raw_html: str) -> str:
    """Extract the <title> tag text from raw HTML, stripped of site name suffixes."""
    m = re.search(r'<title[^>]*>([^<]{3,200})</title>', raw_html, re.I)
    if not m:
        return ""
    title = re.sub(r'\s*[-|—]\s*(BBC|CNN|Reuters|AP News|NBC News|CBS News|ABC News|'
                   r'The New York Times|Washington Post|The Guardian|Britannica)[^\n]*$', '',
                   m.group(1), flags=re.I).strip()
    title = re.sub(r'&amp;', '&', title)
    title = re.sub(r'&#\d+;', '', title)
    return title[:100]


def _fetch_raw_url(url: str, timeout: int = 10) -> str:
    try:
        import ssl as _ssl
        import urllib.request
        _ctx = None
        try:
            import certifi as _certifi
            _ctx = _ssl.create_default_context(cafile=_certifi.where())
        except Exception as ssl_e:
            print(f"[{_ts()} SOURCES] certifi unavailable ({ssl_e}) — SSL unverified")
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36 VerdictIn60/1.0"
                )
            }
        )
        kw = {"context": _ctx} if _ctx else {}
        with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
            data = r.read(350_000)
            return data.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[{_ts()} SOURCES] fetch FAILED — {type(e).__name__}: {e} — url={url[:120]}")
        return ""


def _fetch_search_html(url: str, timeout: int = 12):
    """Like _fetch_raw_url, but also returns the HTTP status code (or None on a
    network-level failure) so callers can react to rate-limiting (e.g. 429)."""
    import ssl as _ssl
    import urllib.error
    import urllib.request
    _ctx = None
    try:
        import certifi as _certifi
        _ctx = _ssl.create_default_context(cafile=_certifi.where())
    except Exception:
        pass
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36 VerdictIn60/1.0"
            )
        }
    )
    kw = {"context": _ctx} if _ctx else {}
    try:
        with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
            data = r.read(350_000)
            return data.decode("utf-8", errors="replace"), r.status
    except urllib.error.HTTPError as e:
        return "", e.code
    except Exception as e:
        print(f"[{_ts()} SOURCES] search fetch FAILED — {type(e).__name__}: {e} — url={url[:120]}")
        return "", None


def _find_browser_executable() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("msedge"),
    ]
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    return ""


def _fetch_playwright_rendered_html(url: str, timeout: int = 24) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""

    try:
        with sync_playwright() as p:
            browser = None
            launch_errors = []
            launch_args = [
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-crash-reporter",
                "--disable-software-rasterizer",
            ]
            for launch_kwargs in (
                {"channel": "chrome", "headless": True, "args": launch_args},
                {"headless": True, "args": launch_args},
            ):
                try:
                    browser = p.chromium.launch(**launch_kwargs)
                    break
                except Exception as e:
                    launch_errors.append(str(e).splitlines()[0])
            if browser is None:
                print(
                    f"[{_ts()} SOURCES] Playwright browser unavailable: "
                    f"{'; '.join(launch_errors)[:220]}"
                )
                return ""
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                viewport={"width": 1365, "height": 900},
            )
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(2500)
            html = page.content()
            browser.close()
            if html and len(html) > 500:
                print(f"[{_ts()} SOURCES] Playwright reader loaded {len(html)} bytes: {url[:90]}")
                return html
    except Exception as e:
        print(f"[{_ts()} SOURCES] Playwright reader failed: {type(e).__name__}: {e}")
    return ""


def _fetch_browser_rendered_html(url: str, timeout: int = BROWSER_FETCH_TIMEOUT) -> str:
    """Render a public page with a real browser engine and return its DOM.

    This is a fallback for news sites that block urllib/requests but still load
    in a normal browser. It does not bypass paywalls or captchas.

    Exactly one rendering attempt is made (Playwright, or — if Playwright isn't
    available — a single headless Chrome/Chromium DOM dump). Never retries with
    a second browser-launch variant; a slow/blocked page should fail fast so the
    caller can mark it Blocked/Inaccessible instead of stalling the investigation.
    """
    html = _fetch_playwright_rendered_html(url, timeout=timeout)
    if html:
        return html

    browser = _find_browser_executable()
    if not browser:
        print(f"[{_ts()} SOURCES] browser reader unavailable: Chrome/Chromium not found")
        return ""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="verdictin60-browser-") as profile_dir:
        cmd = [
            browser,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-crash-reporter",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_dir}",
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            f"--virtual-time-budget={int(timeout * 1000)}",
            "--dump-dom",
            url,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            html = r.stdout or ""
            if r.returncode == 0 and len(html) > 500:
                print(f"[{_ts()} SOURCES] browser reader loaded {len(html)} bytes: {url[:90]}")
                return html
            stderr = (r.stderr or "").strip().splitlines()
            detail = stderr[-1] if stderr else f"returncode={r.returncode}"
            print(f"[{_ts()} SOURCES] browser reader failed: {detail[:160]}")
        except Exception as e:
            print(f"[{_ts()} SOURCES] browser reader exception: {type(e).__name__}: {e}")
    return ""


def _load_source_cache() -> dict:
    try:
        if SOURCE_CACHE_PATH.exists():
            return json.loads(SOURCE_CACHE_PATH.read_text())
    except Exception as e:
        print(f"[{_ts()} SOURCES] source cache read failed: {e}")
    return {"searches": {}}


def _save_source_cache(cache: dict):
    try:
        SOURCE_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        print(f"[{_ts()} SOURCES] source cache write failed: {e}")


def _search_web(query: str, limit: int = 6) -> list:
    """Search the web and return a list of {title, url, query, engine} dicts.

    Engine priority:
      1. Mojeek — returns plain static HTML, no bot-blocking
      2. DuckDuckGo HTML — fallback; DDG increasingly blocks scrapers
      3. Bing — last resort; JS-heavy but sometimes useful
    """
    import html as _html
    import urllib.parse

    qenc = urllib.parse.quote(query)
    cache = _load_source_cache()
    cache_key = re.sub(r"\s+", " ", query.strip().lower())
    cached = cache.get("searches", {}).get(cache_key)
    if cached:
        age_seconds = time.time() - float(cached.get("saved_at", 0))
        if age_seconds < 7 * 24 * 60 * 60 and cached.get("results"):
            print(f"[{_ts()} SOURCES] search cache HIT: {query}")
            return cached.get("results", [])[:limit]

    # Each entry: (engine_name, fetch_url, [(href_group, title_group), ...])
    # Patterns must capture exactly 2 groups: (href, title_text).
    engines = [
        (
            "brave",
            f"https://search.brave.com/search?q={qenc}",
            [
                r'<a[^>]+href="(https?://[^"]{10,240})"[^>]*>(.*?)</a>',
            ],
        ),
        (
            "google_news",
            f"https://news.google.com/rss/search?q={qenc}&hl=en-US&gl=US&ceid=US:en",
            [],
        ),
        (
            "mojeek",
            f"https://www.mojeek.com/search?q={qenc}&safe=0",
            # Mojeek result links are plain <a href="https://...">Title text</a>
            # outside of nav/sidebar — match any external href with adjacent text.
            [r'href="(https?://(?!(?:www\.)?mojeek\.com)[^"]{10,200})"[^>]*>([^<]{5,120})'],
        ),
        (
            "duckduckgo",
            f"https://duckduckgo.com/html/?q={qenc}",
            [
                r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                r'class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                # newer DDG HTML layout
                r'href="(https?://[^"]{10,200})"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>',
            ],
        ),
        (
            "bing",
            f"https://www.bing.com/search?q={qenc}",
            [
                r'<h2[^>]*>\s*<a[^>]+href="(https?://[^"]{10,200})"[^>]*>(.*?)</a>',
                # Bing sometimes uses data-href instead of href
                r'data-href="(https?://[^"]{10,200})"[^>]*>\s*([^<]{5,120})',
            ],
        ),
    ]

    _SKIP_DOMAINS = frozenset([
        "duckduckgo.com", "bing.com", "microsoft.com",
        "google.com", "mojeek.com", "brave.com",
        # Yahoo results (search pages, mail, yahoo.com/news, etc.) are filtered
        # out entirely — noisy and rarely case-specific.
        "yahoo.com",
        "blocksurvey.io", "buttondown.email",
        "blog.mojeek.com", "community.mojeek.com",
    ])

    def _clean_href(href: str) -> str:
        href = href.replace("&amp;", "&")
        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            qs     = urllib.parse.parse_qs(parsed.query)
            href   = qs.get("uddg", [href])[0]
        if "r.search.yahoo.com" in href and "/RU=" in href:
            try:
                encoded = href.split("/RU=", 1)[1].split("/RK=", 1)[0]
                href = urllib.parse.unquote(encoded)
            except Exception:
                pass
        return urllib.parse.unquote(href)

    seen    = set()
    results = []

    for engine, url, patterns in engines:
        if len(results) >= limit:
            break
        if engine == "brave" and _brave_in_backoff():
            print(f"[{_ts()} SOURCES] {engine}: skipped (rate-limit backoff active)")
            continue
        print(f"[{_ts()} SOURCES] searching {engine}: {url[:140]}")
        raw_html, status = _fetch_search_html(url, timeout=12)
        if engine == "brave" and status == 429:
            _set_brave_backoff()
            continue
        if not raw_html:
            print(f"[{_ts()} SOURCES] {engine}: empty response (blocked or SSL error, status={status})")
            continue
        matched = 0
        if engine == "google_news":
            for item in re.findall(r"<item>(.*?)</item>", raw_html, re.I | re.S):
                title_m = re.search(r"<title>(.*?)</title>", item, re.I | re.S)
                link_m = re.search(r"<link>(https://news\.google\.com/rss/articles/[^<]+)</link>", item, re.I | re.S)
                if not title_m or not link_m:
                    continue
                href = _html.unescape(link_m.group(1)).strip()
                title = _strip_html_text(_html.unescape(title_m.group(1)))
                if href in seen:
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "query": query, "engine": engine})
                matched += 1
                if len(results) >= limit:
                    break
            print(f"[{_ts()} SOURCES] {engine}: {matched} result(s) matched (html={len(raw_html)} bytes)")
            if len(results) >= limit:
                break
            continue
        for pattern in patterns:
            for m in re.finditer(pattern, raw_html, re.I | re.S):
                href, title_html = m.groups()
                href  = _clean_href(href)
                title = _strip_html_text(title_html)
                if not href.startswith("http") or href in seen:
                    continue
                domain = urllib.parse.urlparse(href).netloc.lower().lstrip("www.")
                if domain != "news.google.com" and any(skip in domain for skip in _SKIP_DOMAINS):
                    continue
                seen.add(href)
                results.append({"title": title, "url": href, "query": query, "engine": engine})
                matched += 1
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        print(f"[{_ts()} SOURCES] {engine}: {matched} result(s) matched (html={len(raw_html)} bytes)")
        relevant = [
            r for r in results
            if any(term.strip('"').lower() in (r.get("title", "") + " " + r.get("url", "")).lower()
                   for term in query.split()
                   if len(term.strip('"')) >= 4)
        ]
        if len(relevant) >= limit:
            # Got something from this engine — don't bother with lower-priority engines
            break

    if results:
        cache.setdefault("searches", {})[cache_key] = {
            "saved_at": time.time(),
            "query": query,
            "results": results[:12],
        }
        _save_source_cache(cache)

    return results


def _ddg_search(query: str, limit: int = 5) -> list:
    return _search_web(query, limit=limit)


def _fetch_wiki_citations(case_name: str) -> list:
    """Return a list of external URLs cited in a Wikipedia article.

    Uses the Wikipedia Action API (wikitext) so we get raw citation URLs without
    needing to scrape a rendered page. Returns [] on any error.
    """
    import json as _json, urllib.parse as _up, urllib.request as _ur, ssl as _ssl
    try:
        import certifi as _cf
        _ctx = _ssl.create_default_context(cafile=_cf.where())
    except Exception:
        _ctx = None
    try:
        api_url = (
            "https://en.wikipedia.org/w/api.php?action=query&titles="
            + _up.quote(case_name.replace(" ", "_"))
            + "&prop=revisions&rvprop=content&rvslots=main"
            + "&format=json&formatversion=2"
        )
        req = _ur.Request(api_url, headers={"User-Agent": "VerdictIn60/1.0 (contact@verdictin60.com)"})
        kw  = {"context": _ctx} if _ctx else {}
        with _ur.urlopen(req, timeout=12, **kw) as r:
            data = _json.loads(r.read())
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return []
        wikitext = (
            pages[0]
            .get("revisions", [{}])[0]
            .get("slots", {})
            .get("main", {})
            .get("content", "")
        )
        # Extract URLs from |url= parameters and bare [[url]] references.
        # Skip archive.org mirrors — we prefer the live source.
        urls_raw  = re.findall(r'url\s*=\s*(https?://[^\s|}\]]{10,250})', wikitext)
        urls_raw += re.findall(r'\[(https?://[^\s\]]{10,250})', wikitext)
        seen, urls = set(), []
        for u in urls_raw:
            u = u.strip().rstrip('.')
            if u in seen:
                continue
            seen.add(u)
            if "web.archive.org" in u:
                continue
            urls.append(u)
        print(f"[{_ts()} SOURCES] Wikipedia citations: {len(urls)} unique URLs for {case_name!r}")
        return urls
    except Exception as e:
        print(f"[{_ts()} SOURCES] _fetch_wiki_citations error: {e}")
        return []


def _search_courtlistener(case_name: str, limit: int = 5) -> list:
    """Search CourtListener for legal opinions mentioning the case.

    Returns a list of {title, url} dicts. CourtListener's HTML search is
    publicly accessible without authentication.
    """
    import urllib.parse as _up
    q   = _up.quote(f'"{case_name}"')
    url = f"https://www.courtlistener.com/?q={q}&type=o&order_by=score+desc"
    print(f"[{_ts()} SOURCES] CourtListener search: {url[:120]}")
    html = _fetch_raw_url(url, timeout=12)
    if not html:
        return []
    results = []
    for m in re.finditer(
        r'href="(/opinion/\d+/[a-z0-9-]+/)[^"]*"[^>]*>\s*(?:<[^>]+>)*\s*([^<]{3,120})',
        html, re.S
    ):
        path  = m.group(1)
        title = re.sub(r'\s+', ' ', m.group(2)).strip()
        if not title or title.startswith('<'):
            continue
        full_url = f"https://www.courtlistener.com{path}"
        if full_url not in {r['url'] for r in results}:
            results.append({"title": title[:80], "url": full_url})
            if len(results) >= limit:
                break
    print(f"[{_ts()} SOURCES] CourtListener: {len(results)} opinion(s) found")
    return results


# ── Source classification ─────────────────────────────────────────────────────
# Maps a URL + title to one of 5 tier labels.
# Tier 1 = Official, Tier 2 = Reporting, Tier 3 = Investigative,
# Tier 4 = Agency, Tier 5 = Encyclopedia.  Unrecognised = "Reference".

_TIER1_OFFICIAL = (
    ".gov", "police", "sheriff", "district-attorney", "districtattorney",
    "prosecutor", "justice.gov", "courts.gov", "supremecourt", "appeals",
    "coroner", "medical-examiner", "medicalexaminer", "prison", "corrections",
    "missingpersons", "namus.gov", "fbi.gov", "dea.gov",
    "bundesgericht", "staatsanwaltschaft", "lincolncountymt",
)
_TIER2_REPORTING = (
    "abcnews.go.com", "nbcnews.com", "cbsnews.com", "cnn.com",
    "apnews.com", "reuters.com", "bbc.co", "bbc.com",
    "courttv.com", "dateline", "48hours", "today.com", "people.com",
    "usatoday.com", "washingtonpost.com", "nytimes.com", "latimes.com",
    "theguardian.com", "chicagotribune.com", "nypost.com",
    # common local station patterns
    "wate.com", "wvlt.tv", "wbir.com", "wsmv.com", "wkrn.com",
    "nbcmontana.com", "kpax.com", "ktvq.com", "kulr8.com", "krtv.com",
    "montanarightnow.com", "flatheadbeacon.com", "dailyinterlake.com",
    "missoulian.com", "billingsgazette.com", "wset.com", "abcnews4.com",
)
_TIER3_INVESTIGATIVE = (
    "newyorker.com", "rollingstone.com", "propublica.org",
    "texasmonthly.com", "theatlantic.com", "vanityfair.com",
    "motherjones.com", "thedailybeast.com",
)
_TIER4_AGENCY = (
    "fbi.gov", "dea.gov", "interpol.int", "ncmec.org",
    "uscourts.gov", "courtlistener.com", "justia.com",
    "law.justia.com", "oyez.org", "findlaw.com", "caselaw.",
)
_TIER5_ENCYCLOPEDIA = (
    "britannica.com",
)

# Entertainment / pop-culture / general-interest blog domains. Checked FIRST
# and force-classified as "Reference" so they can never be mis-tagged Official
# or Agency, no matter what a headline says (e.g. an article title mentioning
# "court" or "prison" on a site like ScreenRant).
_ENTERTAINMENT_BLOG_DOMAINS = (
    "screenrant.com", "cbr.com", "gamerant.com", "collider.com",
    "comicbookmovie.com", "ign.com", "kotaku.com", "polygon.com",
    "thethings.com", "looper.com", "ranker.com", "distractify.com",
    "buzzfeed.com", "showbiz411.com",
)


def _classify_source(url: str, title: str = "") -> str:
    """Return the tier label for a URL.

    Every tier rule matches against the URL's domain only — never the
    headline/title text — so a headline that happens to mention "court" or
    "prison" can't get an unrelated blog mis-tagged as Official/Agency.
    Wikipedia is always excluded externally.
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower().lstrip("www.")

    if any(m in domain for m in _ENTERTAINMENT_BLOG_DOMAINS):
        return "Reference"
    # Tier 4 legal databases checked before generic "official" so Justia etc.
    # aren't mis-tagged as Official.
    if any(m in domain for m in _TIER4_AGENCY):
        return "Agency"
    if any(m in domain for m in _TIER1_OFFICIAL):
        return "Official"
    if any(m in domain for m in _TIER2_REPORTING):
        return "Reporting"
    if any(m in domain for m in _TIER3_INVESTIGATIVE):
        return "Investigative"
    if any(m in domain for m in _TIER5_ENCYCLOPEDIA):
        return "Encyclopedia"
    if re.search(r"\.(gov|us)$", domain) or any(
        marker in domain for marker in ("sheriff", "police", "county", "da-", "districtattorney")
    ):
        return "Official"
    blog_hints = ("reddit", "youtube", "tiktok", "spotify", "podcast", "blogspot", "medium.com")
    if any(h in domain for h in blog_hints):
        return "Reference"
    station_like = re.match(r"^(?:k|w)[a-z0-9]{2,5}\.(?:com|tv|org|net)$", domain)
    if station_like:
        return "Reporting"
    return "Reference"


def gather_verification_sources(case_name: str, original_context: str,
                                wiki_title: str = "", wiki_facts: str = "",
                                deadline_seconds: float = None,
                                max_sources: int = None,
                                stats: dict = None) -> list:
    """Gather sources using a strict 5-tier priority system.

    Strategy (in order):
      1. Official/government/court-oriented web searches
      2. CourtListener direct legal search
      3. Extract citation URLs from the Wikipedia article as discovery leads
      4. Reputable reporting and investigative searches

    Tier labels (for source_section_for_caption):
      Official      — .gov, police, DA, court records, medical examiner
      Reporting     — AP, Reuters, BBC, ABC/NBC/CBS/CNN, local news
      Investigative — New Yorker, Rolling Stone, ProPublica, Texas Monthly
      Agency        — FBI/DEA/Interpol/NCMEC, CourtListener, Justia, Oyez
      Encyclopedia  — Britannica (orientation only, never cited as a source)

    Wikipedia is orientation context only — never returned as a citable source.
    Stops early once ≥2 Tier-1/2 (Official + Reporting) sources are secured.

    `deadline_seconds` / `max_sources` are optional budgets (existing callers
    that omit them keep the previous unlimited behavior). When `stats` is
    passed a dict, it is filled in-place with `elapsed_seconds`,
    `sources_checked`, `skipped_slow_or_blocked`, and `stopped_reason` so a
    caller (e.g. the Research Hub UI) can surface "slow/blocked source
    skipped" status to the user.
    """
    first_name = case_name.split()[0].lower() if case_name.split() else ""
    last_name  = case_name.split()[-1].lower() if case_name.split() else ""
    sources: list  = []
    seen_urls: set = set()

    t_start = time.time()
    _budget = {"checked": 0, "skipped_slow_or_blocked": 0, "stopped_reason": ""}

    def _budget_exceeded() -> bool:
        if deadline_seconds is not None and (time.time() - t_start) >= deadline_seconds:
            if not _budget["stopped_reason"]:
                _budget["stopped_reason"] = f"time budget of {deadline_seconds:.0f}s reached"
            return True
        if max_sources is not None and _budget["checked"] >= max_sources:
            if not _budget["stopped_reason"]:
                _budget["stopped_reason"] = f"source budget of {max_sources} sources reached"
            return True
        return False

    def _finish(reason: str = "") -> list:
        if reason and not _budget["stopped_reason"]:
            _budget["stopped_reason"] = reason
        if stats is not None:
            stats["elapsed_seconds"] = round(time.time() - t_start, 1)
            stats["sources_checked"] = _budget["checked"]
            stats["skipped_slow_or_blocked"] = _budget["skipped_slow_or_blocked"]
            stats["stopped_reason"] = _budget["stopped_reason"]
        return sources

    def _normalize(s: str) -> str:
        """Lowercase + strip accents for accent-insensitive matching."""
        import unicodedata
        return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

    _name_norm      = _normalize(case_name)
    _first_norm     = _normalize(first_name)
    _last_norm      = _normalize(last_name)
    _wiki_title_norm = _normalize(wiki_title or "")

    context_terms = []
    for m in re.finditer(
        r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'.-]{2,}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'.-]{2,}){0,2}\b",
        original_context[:1400]
    ):
        term = m.group(0).strip()
        norm = _normalize(term)
        if len(norm) < 4:
            continue
        if norm in {
            "according", "investigators", "january", "february", "march",
            "april", "june", "july", "august", "september", "october",
            "november", "december"
        }:
            continue
        if norm not in context_terms:
            context_terms.append(norm)
        if len(context_terms) >= 10:
            break

    def _name_in(text: str) -> bool:
        tn = _normalize(text)
        if _name_norm and _name_norm in tn:
            return True
        if _wiki_title_norm and _wiki_title_norm in tn:
            return True
        if _first_norm and _last_norm and _first_norm in tn and _last_norm in tn:
            return True
        if _last_norm and len(_last_norm) >= 5 and _last_norm in tn:
            return True
        context_hits = sum(1 for term in context_terms if term in tn)
        return context_hits >= 2

    def _is_pdf_url(url: str) -> bool:
        return url.lower().split("?")[0].endswith(".pdf")

    def _is_paywalled_domain(url: str) -> bool:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return any(p in domain for p in _PAYWALLED_DOMAINS)

    def _add_source(url: str, title: str, tier_label: str) -> bool:
        """Fetch a URL, check it mentions the case, classify and append. Returns True if added."""
        if url in seen_urls or "wikipedia.org" in url.lower():
            return False
        seen_urls.add(url)
        _budget["checked"] += 1

        if _is_pdf_url(url):
            # PDFs are downloaded directly (with a timeout) and marked as a PDF
            # source — never rendered through a browser DOM dump.
            print(f"[{_ts()} SOURCES] fetching PDF ({tier_label}): {url[:110]}")
            raw = _fetch_raw_url(url, timeout=DIRECT_FETCH_TIMEOUT)
            kind = _classify_source(url, title)
            if not raw:
                _budget["skipped_slow_or_blocked"] += 1
                if not _name_in(f"{title} {url}"):
                    return False
                sources.append({
                    "title": title or url[:80], "url": url, "kind": kind, "tier": kind,
                    "text": "", "blocked": True, "is_pdf": True,
                    "inaccessible_reason": "PDF source could not be downloaded within the timeout",
                })
                return False
            sources.append({
                "title": title or _page_title(raw) or url[:80], "url": url, "kind": kind,
                "tier": kind, "text": "", "blocked": False, "is_pdf": True, "reader": "pdf",
            })
            print(f"[{_ts()} SOURCES] ADDED PDF ({kind}): {(title or url)[:65]}")
            return True

        print(f"[{_ts()} SOURCES] fetching ({tier_label}): {url[:110]}")
        raw = _fetch_raw_url(url, timeout=DIRECT_FETCH_TIMEOUT)
        reader = "direct"
        text = _extract_readable_text(raw)[:5000] if raw else ""
        if raw and (_looks_like_block_page(text) or len(text) < 450):
            print(f"[{_ts()} SOURCES] direct fetch looked blocked/thin, trying browser reader: {url[:90]}")
            raw = ""
            text = ""
        if not raw and _is_paywalled_domain(url):
            # Known paywalled domain — a browser render never gets past the
            # paywall, so don't burn a ~9s fallback attempt on it.
            print(f"[{_ts()} SOURCES] known paywalled domain, skipping browser fallback: {url[:90]}")
            _budget["skipped_slow_or_blocked"] += 1
        elif not raw:
            browser_raw = _fetch_browser_rendered_html(url, timeout=BROWSER_FETCH_TIMEOUT)
            browser_text = _extract_readable_text(browser_raw)[:5000] if browser_raw else ""
            if browser_raw and not _looks_like_block_page(browser_text) and len(browser_text) >= 450:
                raw = browser_raw
                text = browser_text
                reader = "browser"
            else:
                print(f"[{_ts()} SOURCES] empty/blocked response after browser reader: {url[:90]}")
                _budget["skipped_slow_or_blocked"] += 1

        if not raw:
            if not _name_in(f"{title} {url}"):
                print(f"[{_ts()} SOURCES] blocked source not case-specific, skipping: {url[:90]}")
                return False
            kind = _classify_source(url, title)
            sources.append({
                "title": title or url[:80],
                "url": url,
                "kind": kind,
                "tier": kind,
                "text": "",
                "blocked": True,
                "inaccessible_reason": "Source found but inaccessible to the app",
            })
            return False
        if not title:
            title = _page_title(raw)
        if not _name_in(f"{title} {url} {text}"):
            print(f"[{_ts()} SOURCES] case name not in page, skipping: {url[:90]}")
            return False
        kind = _classify_source(url, title)
        sources.append({
            "title": title or url[:80],
            "url": url,
            "kind": kind,
            "tier": kind,
            "text": text[:4500],
            "blocked": False,
            "reader": reader,
        })
        print(f"[{_ts()} SOURCES] ADDED ({kind}, {reader}): {title[:65]}")
        return True

    def _add_discovered_source(url: str, title: str, tier_label: str) -> bool:
        """Keep a case-specific search result when full-page fetch is unavailable."""
        if url in seen_urls or "wikipedia.org" in url.lower():
            return False
        if not _name_in(f"{title} {url}"):
            return False
        kind = _classify_source(url, title)
        if kind == "Reference":
            return False
        seen_urls.add(url)
        sources.append({
            "title": title or url[:80],
            "url": url,
            "kind": kind,
            "tier": kind,
            "text": "",
            "blocked": True,
            "discovered_only": True,
            "inaccessible_reason": "Source discovered in search results; full page was not accessible to the app",
        })
        print(f"[{_ts()} SOURCES] DISCOVERED ({kind}): {(title or url)[:65]}")
        return True

    def _high_quality_count() -> int:
        return sum(
            1 for s in sources
            if s.get("kind") in ("Official", "Reporting") and not s.get("blocked")
        )

    def _accessible_count() -> int:
        return sum(1 for s in sources if not s.get("blocked") and s.get("tier") != "Wikipedia")

    def _is_discovery_only_result(result: dict) -> bool:
        return (
            result.get("engine") == "google_news"
            or "news.google.com/rss/articles/" in result.get("url", "")
        )

    # ── Step 1: Official / legal web search ──────────────────────────────────
    print(f"[{_ts()} SOURCES] === Step 1: Official/legal source search ===")
    context = original_context[:1800]
    location_terms = []
    year_terms = re.findall(r"\b(?:18|19|20)\d{2}\b", context)
    for word in (
        "New York", "Manhattan", "Long Island", "Tennessee", "Knoxville",
        "Florida", "Texas", "California", "Pennsylvania", "Philadelphia",
        "Ohio", "Georgia", "North Carolina", "South Carolina", "Virginia",
        "Kentucky", "Missouri", "Illinois", "Germany", "North Korea",
        "Montana", "Bull Lake", "Lincoln County",
    ):
        if re.search(rf"\b{re.escape(word)}\b", context, re.I):
            location_terms.append(word)

    official_queries = [
        ("Official", f'"{case_name}" police sheriff prosecutor "district attorney" court'),
        ("Official", f'"{case_name}" indictment sentencing appeal "court records"'),
        ("Official", f'"{case_name}" "sheriff" "missing"'),
        ("Official", f'"{case_name}" "Lincoln County Sheriff"'),
        ("Agency", f'"{case_name}" CourtListener Justia FindLaw caselaw'),
    ]
    if year_terms:
        official_queries.append(("Official", f'"{case_name}" "{year_terms[0]}" court police prosecutor'))
    for loc in location_terms[:3]:
        official_queries.append(("Official", f'"{case_name}" "{loc}" court police prosecutor'))

    for tier_label, query in official_queries:
        if _budget_exceeded():
            return _finish()
        print(f"[{_ts()} SOURCES] query ({tier_label}): {query}")
        for result in _search_web(query, limit=4):
            if _budget_exceeded():
                return _finish()
            if _is_discovery_only_result(result):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            elif not _add_source(result["url"], result.get("title", ""), tier_label):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            if _high_quality_count() >= 2:
                print(f"[{_ts()} SOURCES] Early exit after official/legal search: {_high_quality_count()} Tier-1/2")
                return _finish("sufficient high-quality sources found")

    # ── Step 2: CourtListener direct search ───────────────────────────────────
    print(f"[{_ts()} SOURCES] === Step 2: CourtListener direct search ===")
    for cl_result in _search_courtlistener(case_name, limit=4):
        if _budget_exceeded():
            return _finish()
        _add_source(cl_result["url"], cl_result["title"], "Agency")
        if _high_quality_count() >= 2:
            print(f"[{_ts()} SOURCES] Early exit after CourtListener: {_high_quality_count()} Tier-1/2")
            return _finish("sufficient high-quality sources found")

    # ── Step 3: Wikipedia citations ───────────────────────────────────────────
    # Wikipedia's wikitext contains curated references with real source URLs —
    # BBC, AP, Reuters, CNN, .gov sites, etc. — all without needing search engines.
    lookup_name = wiki_title or case_name
    print(f"[{_ts()} SOURCES] === Step 3: Wikipedia citations for {lookup_name!r} ===")
    wiki_urls = _fetch_wiki_citations(lookup_name)

    # Classify each citation URL and process highest tiers first
    tier_order_map = {"Official": 0, "Reporting": 1, "Investigative": 2, "Agency": 3,
                      "Encyclopedia": 4, "Reference": 5}
    def _url_tier_priority(url: str) -> int:
        t = _classify_source(url, "")
        return tier_order_map.get(t, 5)

    wiki_urls_sorted = sorted(wiki_urls, key=_url_tier_priority)

    for url in wiki_urls_sorted:
        if _budget_exceeded():
            return _finish()
        tier_label = _classify_source(url, "")
        if tier_label == "Encyclopedia":
            continue   # Britannica etc — skip, not useful as an independent source
        # "Reference" = unrecognised domain but still a real citation from Wikipedia;
        # attempt it and let _add_source decide if the content is relevant.
        _add_source(url, "", tier_label)
        if _high_quality_count() >= 2:
            print(f"[{_ts()} SOURCES] Early exit after Wiki citations: {_high_quality_count()} Tier-1/2")
            return _finish("sufficient high-quality sources found")

    # ── Step 4: Reporting / investigative search fallback ───────────────────
    # This is intentionally after citations + legal search. It catches cases
    # where Wikipedia cites blocked newspaper pages, or where a local station /
    # court page is discoverable but not cited.
    print(f"[{_ts()} SOURCES] === Step 4: Reporting/investigative search ===")
    query_plan = [
        ("Reporting", f'"{case_name}"'),
        ("Reporting", f'"{case_name}" missing found investigation'),
        ("Reporting", f'"{case_name}" AP Reuters BBC ABC NBC CBS CNN'),
        ("Reporting", f'"{case_name}" CNN NBC CBS ABC'),
        ("Reporting", f'"{case_name}" "NBC Montana" KPAX KTVQ KULR KRTV'),
        ("Reporting", f'"{case_name}" local news newspaper "New York Times"'),
        ("Investigative", f'"{case_name}" ProPublica "The New Yorker" "Rolling Stone" documentary'),
    ]
    for loc in location_terms[:3]:
        query_plan.insert(1, ("Reporting", f'"{case_name}" "{loc}" news newspaper'))
    if year_terms:
        query_plan.insert(1, ("Reporting", f'"{case_name}" "{year_terms[0]}" news newspaper'))

    for tier_label, query in query_plan:
        if _budget_exceeded():
            return _finish()
        print(f"[{_ts()} SOURCES] query ({tier_label}): {query}")
        for result in _search_web(query, limit=5):
            if _budget_exceeded():
                return _finish()
            if _is_discovery_only_result(result):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            elif not _add_source(result["url"], result.get("title", ""), tier_label):
                _add_discovered_source(result["url"], result.get("title", ""), tier_label)
            if _high_quality_count() >= 2:
                print(f"[{_ts()} SOURCES] Early exit after reporting search: {_high_quality_count()} Tier-1/2")
                return _finish("sufficient high-quality sources found")

    print(f"[{_ts()} SOURCES] Search complete: {len(sources)} source(s), "
          f"{_high_quality_count()} high-quality, {_accessible_count()} accessible")

    # ── Step 4: Wikipedia orientation fallback (last resort) ──────────────────
    if wiki_facts and not any(not s.get("blocked") for s in sources):
        wiki_url = "https://en.wikipedia.org/wiki/" + (wiki_title or case_name).replace(" ", "_")
        sources.append({
            "title": wiki_title or f"Wikipedia: {case_name}",
            "url": wiki_url,
            "kind": "Orientation only",
            "tier": "Wikipedia",
            "text": wiki_facts[:5000],
        })

    return _finish("all search steps completed")


def format_sources_for_prompt(sources: list) -> str:
    """Format sources for the AI caption prompt, excluding pure orientation entries."""
    usable = [
        s for s in sources
        if s.get("tier") not in ("Wikipedia",) and not s.get("blocked")
    ]
    if not usable:
        # Fall back to Wikipedia orientation if it's all we have
        usable = [s for s in sources if not s.get("blocked")]
    if not usable:
        return "No independent sources found."
    blocks = []
    for i, src in enumerate(usable, 1):
        blocks.append(
            f"[{i}] {src.get('title','Source')} "
            f"(Tier: {src.get('tier','?')} / {src.get('kind','Reference')})\n"
            f"URL: {src.get('url','')}\n"
            f"TEXT: {src.get('text','')[:2500]}"
        )
    return "\n\n".join(blocks)


def format_blocked_sources_for_prompt(sources: list) -> str:
    blocked = [s for s in sources if s.get("blocked")]
    if not blocked:
        return "None."
    lines = []
    for src in blocked[:8]:
        lines.append(
            f"- {src.get('title','Source')} ({src.get('kind','Reference')})\n"
            f"  URL: {src.get('url','')}\n"
            f"  Reason: {src.get('inaccessible_reason','Inaccessible')}"
        )
    return "\n".join(lines)


def verification_confidence(sources: list) -> tuple[str, str]:
    accessible = [
        s for s in sources
        if not s.get("blocked") and s.get("tier") != "Wikipedia"
    ]
    official = [s for s in accessible if s.get("kind") == "Official"]
    reporting = [s for s in accessible if s.get("kind") == "Reporting"]
    agency = [s for s in accessible if s.get("kind") == "Agency"]
    investigative = [s for s in accessible if s.get("kind") == "Investigative"]
    reliable = official + reporting + agency + investigative
    blocked = [s for s in sources if s.get("blocked")]
    wiki_only = bool(sources) and not accessible and any(s.get("tier") == "Wikipedia" for s in sources)

    if official and len(reliable) >= 2:
        return "High", "Official source plus multiple accessible sources."
    if len(reporting) >= 2 or (reporting and (official or agency or investigative)):
        return "Medium", "Multiple accessible sources, including reputable reporting."
    if reporting or agency or investigative:
        return "Low", "Only one accessible reliable source was found."
    if blocked and not accessible:
        return "Low", "Reliable-looking sources were discovered but inaccessible."
    if wiki_only:
        return "Low", "Only encyclopedia orientation was accessible."
    return "Very low", "Only the original video caption or weak context is available."


def build_verified_fact_sheet(case_name: str, sources: list) -> str:
    accessible = [
        s for s in sources
        if not s.get("blocked") and s.get("tier") != "Wikipedia"
    ]
    lines = [
        f"Case title: {case_name}",
        "Victim: Use only if explicitly supported by accessible sources.",
        "Suspect: Use only if explicitly supported by accessible sources.",
        "Location: Use only if explicitly supported by accessible sources.",
        "Year: Use only if explicitly supported by accessible sources.",
        "Crime type: Use only if explicitly supported by accessible sources.",
        "Discovery: Use only if explicitly supported by accessible sources.",
        "Investigation: Use only if explicitly supported by accessible sources.",
        "Court outcome: Use only if explicitly supported by accessible sources.",
        "Sentence: Use only if explicitly supported by accessible sources.",
        "Reliable source URLs:",
    ]
    if accessible:
        for src in accessible[:8]:
            lines.append(f"- {src.get('url','')}")
    else:
        lines.append("- No accessible reliable source found.")
    lines.extend([
        "Unverified details: Any detail found only in the original video caption.",
        "Conflicting details: If sources disagree, phrase generally or omit the detail.",
    ])
    return "\n".join(lines)


def source_section_for_caption(sources: list) -> str:
    """Build the Research & Verification block for the end of every caption.

    Format:
        ━━━━━━━━━━━━━━━
        Research & Verification

        Official:
        • Source name

        Reporting:
        • Source name

    Wikipedia is never listed. If only Wikipedia was found, a note is added instead.
    """
    buckets = {"Official": [], "Reporting": [], "Investigative": [], "Agency": []}
    discovered = {"Official": [], "Reporting": [], "Investigative": [], "Agency": []}
    has_real_sources = False

    def _display_source_name(src: dict) -> str:
        title = src.get("title", "Source").strip() or "Source"
        if src.get("discovered_only"):
            # Google News titles usually end with " - Outlet". Use the outlet
            # name in the public caption so the research block stays polished.
            outlet_m = re.search(r"\s+-\s+([^-\n]{3,60})$", title)
            if outlet_m:
                return outlet_m.group(1).strip()
        return re.split(r"\s+(?:[|—])\s+", title, maxsplit=1)[0].strip() or title

    for src in sources:
        kind = src.get("kind", "Reference")
        tier = src.get("tier", "")
        if src.get("blocked"):
            if src.get("discovered_only") and kind in discovered:
                short = _display_source_name(src)
                if short not in discovered[kind]:
                    discovered[kind].append(short[:70])
            continue
        if tier == "Wikipedia" or kind == "Orientation only":
            continue
        has_real_sources = True
        bucket_key = kind if kind in buckets else None
        if bucket_key is None:
            continue
        short = _display_source_name(src)
        if short not in buckets[bucket_key]:
            buckets[bucket_key].append(short[:70])

    lines = ["━━━━━━━━━━━━━━━", "Research & Verification", ""]
    if buckets["Official"]:
        lines.append("Official:")
        lines.extend(f"• {s}" for s in buckets["Official"][:4])
        lines.append("")
    else:
        lines.append("Official:")
        lines.append("• Public official records were not available in the accessible review materials.")
        lines.append("")
    if buckets["Reporting"]:
        lines.append("Reporting:")
        lines.extend(f"• {s}" for s in buckets["Reporting"][:5])
        lines.append("")
    elif discovered["Reporting"]:
        lines.append("Reporting:")
        lines.extend(f"• {s} (source lead; full article access limited)" for s in discovered["Reporting"][:5])
        lines.append("")
    else:
        lines.append("Reporting:")
        lines.append("• Additional reputable reporting review recommended.")
        lines.append("")
    if buckets["Investigative"]:
        lines.append("Investigative:")
        lines.extend(f"• {s}" for s in buckets["Investigative"][:3])
        lines.append("")
    if buckets["Agency"]:
        lines.append("Agency:")
        lines.extend(f"• {s}" for s in buckets["Agency"][:4])
        lines.append("")

    if not has_real_sources and not any(discovered.values()):
        has_wiki = any(s.get("tier") == "Wikipedia" for s in sources)
        if has_wiki:
            lines.append("Reference note:")
            lines.append("• Encyclopedia material used for orientation only.")

    return "\n".join(lines)
