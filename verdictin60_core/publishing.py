"""Buffer, Internet Archive, and Meta/Instagram publishing helpers, moved from
app.py (Phase 6 refactor, no behavior change).

- instagram_connect / autodetect_instagram_id / fetch_ig_media_metrics: Meta
  Graph API helpers for connecting an Instagram Business Account and pulling
  post metrics.
- _resolve_buffer_org_id / fetch_buffer_scheduled_texts / get_next_available_date /
  next_available_date_safe: Buffer GraphQL helpers used to find the next open
  posting slot and list already-scheduled posts.
- upload_video: upload a finished video to Internet Archive.
- schedule_to_buffer: create a scheduled Buffer post pointing at an
  Internet Archive video URL.
- buffer_video_not_ready / public_url_http_code / wait_for_public_video_url:
  publishing status checks used while Archive.org finishes processing an
  upload before Buffer can read it.
- UploadPendingError: raised when an Archive.org upload isn't yet HTTP-200
  after all polling attempts.
"""
import datetime
import json
import subprocess
import threading
import time
from pathlib import Path

from verdictin60_core.settings import load_settings, save_settings
from verdictin60_core.scheduling import next_post_datetime, batch_post_datetime


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


# ── Instagram / Meta API ──────────────────────────────────────────────────────

def instagram_connect(app_id: str, app_secret: str, short_token: str) -> dict:
    """Exchange short-lived token → long-lived token → Page ID → IG Business ID.
    Returns a dict with keys: long_token, instagram_business_id, log, error (if any)."""
    import requests
    log = []

    # 1. Exchange for long-lived token (60 days)
    r = requests.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
        "grant_type":        "fb_exchange_token",
        "client_id":         app_id,
        "client_secret":     app_secret,
        "fb_exchange_token": short_token,
    }, timeout=15)
    data = r.json()
    log.append(f"[1] Token exchange → {r.status_code}: {json.dumps(data)[:300]}")
    if "error" in data:
        return {"error": f"Token exchange failed: {data['error'].get('message', data['error'])}", "log": log}
    long_token = data.get("access_token", "")
    if not long_token:
        return {"error": "Token exchange returned no access_token", "log": log}

    # 2a. Confirm token identity
    r_me = requests.get("https://graph.facebook.com/v19.0/me", params={
        "fields": "id,name", "access_token": long_token,
    }, timeout=15)
    me = r_me.json()
    log.append(f"[2a] /me → {r_me.status_code}: {json.dumps(me)[:300]}")

    # 2b. Try /me/accounts with full fields
    r2 = requests.get("https://graph.facebook.com/v19.0/me/accounts", params={
        "fields": "id,name,instagram_business_account",
        "access_token": long_token,
    }, timeout=15)
    accounts_data = r2.json()
    log.append(f"[2b] /me/accounts → {r2.status_code}: {json.dumps(accounts_data)[:400]}")
    pages = accounts_data.get("data", [])

    # 2c. If empty, try with limit=100
    if not pages:
        r2b = requests.get("https://graph.facebook.com/v19.0/me/accounts", params={
            "fields": "id,name,instagram_business_account",
            "limit": 100,
            "access_token": long_token,
        }, timeout=15)
        accounts_data2 = r2b.json()
        log.append(f"[2c] /me/accounts?limit=100 → {r2b.status_code}: {json.dumps(accounts_data2)[:400]}")
        pages = accounts_data2.get("data", [])

    if not pages:
        return {
            "error": (
                "No Facebook Pages found. Make sure your Instagram is connected to a "
                "Facebook Page and the token has pages_show_list permission."
            ),
            "long_token": long_token,
            "log": log,
        }

    # Find first page that has an IG business account
    ig_id = ""
    for page in pages:
        ig_id = page.get("instagram_business_account", {}).get("id", "")
        if ig_id:
            log.append(f"[3] Found IG Business Account: {ig_id} on page {page.get('name','?')}")
            break

    if not ig_id:
        # Try fetching instagram_business_account explicitly for each page
        for page in pages:
            pid = page["id"]
            r3 = requests.get(f"https://graph.facebook.com/v19.0/{pid}", params={
                "fields": "instagram_business_account",
                "access_token": long_token,
            }, timeout=15)
            ig_data = r3.json()
            log.append(f"[3] Page {pid} explicit fetch → {json.dumps(ig_data)[:200]}")
            ig_id = ig_data.get("instagram_business_account", {}).get("id", "")
            if ig_id:
                break

    if not ig_id:
        return {
            "error": "No Instagram Business Account linked to any Facebook Page.",
            "long_token": long_token,
            "log": log,
        }

    return {"long_token": long_token, "instagram_business_id": ig_id, "log": log}


def autodetect_instagram_id(long_token: str) -> dict:
    """Try every known approach to find the Instagram Business Account ID.
    Returns: {instagram_business_id, log, error}"""
    import requests
    log = []

    def get(url, params):
        params["access_token"] = long_token
        r = requests.get(url, params=params, timeout=15)
        body = r.json()
        log.append(f"GET {url.replace('https://graph.facebook.com/v19.0','')}"
                   f"?{','.join(k+'='+str(v) for k,v in params.items() if k!='access_token')}"
                   f" → {r.status_code}: {json.dumps(body)[:500]}")
        return body

    def find_ig_in_pages(pages):
        for page in pages:
            ig = page.get("instagram_business_account", {})
            if isinstance(ig, dict) and ig.get("id"):
                return ig["id"], page.get("name", "?")
        return None, None

    BASE = "https://graph.facebook.com/v19.0"

    # Approach 1: /me/accounts with instagram_business_account field
    data1 = get(f"{BASE}/me/accounts", {"fields": "id,name,instagram_business_account", "limit": 100})
    pages1 = data1.get("data", [])
    ig_id, page_name = find_ig_in_pages(pages1)
    if ig_id:
        return {"instagram_business_id": ig_id, "log": log,
                "note": f"Found via /me/accounts on page '{page_name}'"}

    # Approach 2: nested accounts field on /me
    data2 = get(f"{BASE}/me", {"fields": "id,name,accounts{id,name,instagram_business_account}"})
    pages2 = data2.get("accounts", {}).get("data", [])
    ig_id, page_name = find_ig_in_pages(pages2)
    if ig_id:
        return {"instagram_business_id": ig_id, "log": log,
                "note": f"Found via /me?fields=accounts on page '{page_name}'"}

    # Approach 3: for each page from approach 1, fetch instagram_business_account explicitly
    all_pages = pages1 or pages2
    if all_pages:
        for page in all_pages:
            pid = page.get("id")
            if not pid:
                continue
            data3 = get(f"{BASE}/{pid}", {"fields": "id,name,instagram_business_account"})
            ig_id = data3.get("instagram_business_account", {}).get("id", "")
            if ig_id:
                return {"instagram_business_id": ig_id, "log": log,
                        "note": f"Found via explicit page fetch for page {pid}"}
    else:
        log.append("No pages found in any /me/accounts response — token may lack pages_show_list permission")

    # Approach 4: try /me/subscribed_apps (shows what pages token has access to)
    data4 = get(f"{BASE}/me/subscribed_apps", {})
    log.append(f"subscribed_apps data (diagnostic only): {json.dumps(data4)[:300]}")

    return {
        "error": (
            "Could not find an Instagram Business Account automatically.\n\n"
            "To find it manually:\n"
            "• Go to business.facebook.com → Settings → Instagram Accounts\n"
            "• Click your account → copy the ID from the URL\n"
            "  (or Settings → Account → Business Account Info)\n\n"
            "Then paste the numeric ID into the field above."
        ),
        "log": log,
    }


def fetch_ig_media_metrics(ig_business_id: str, long_token: str,
                           case_name: str, scheduled_date: str) -> dict | None:
    """Find the Instagram media post matching case_name/date and return its metrics."""
    import requests

    # Fetch recent media (up to 50)
    r = requests.get(f"https://graph.facebook.com/v19.0/{ig_business_id}/media", params={
        "fields":       "id,caption,timestamp,media_type",
        "limit":        50,
        "access_token": long_token,
    }, timeout=15)
    media_list = r.json().get("data", [])
    if not media_list:
        return None

    # Match by scheduled_date (post timestamp) or caption containing case name
    target_date = scheduled_date[:10] if scheduled_date else ""
    matched_id = None
    for item in media_list:
        ts = item.get("timestamp", "")[:10]
        caption = item.get("caption", "").lower()
        name_lower = case_name.lower()
        if ts == target_date or name_lower in caption:
            matched_id = item["id"]
            break

    if not matched_id:
        return None

    # Fetch insights for that media
    r2 = requests.get(f"https://graph.facebook.com/v19.0/{matched_id}/insights", params={
        "metric":       "video_views,likes,comments,reach",
        "access_token": long_token,
    }, timeout=15)
    insights = r2.json().get("data", [])
    metrics = {}
    for item in insights:
        metrics[item["name"]] = item.get("values", [{}])[-1].get("value", 0)

    # Also try direct fields for likes/comments (more reliable)
    r3 = requests.get(f"https://graph.facebook.com/v19.0/{matched_id}", params={
        "fields":       "like_count,comments_count",
        "access_token": long_token,
    }, timeout=15)
    direct = r3.json()
    return {
        "views":    metrics.get("video_views", "—"),
        "likes":    direct.get("like_count",    metrics.get("likes", "—")),
        "comments": direct.get("comments_count", metrics.get("comments", "—")),
        "reach":    metrics.get("reach", "—"),
        "media_id": matched_id,
    }


# ── Buffer scheduling helpers ─────────────────────────────────────────────────

def _resolve_buffer_org_id(buffer_key: str, channel_id: str) -> str:
    """Fetch and cache the Buffer organizationId for channel_id."""
    s = load_settings()
    cached = (s.get("buffer_organization_id") or "").strip()
    if cached:
        return cached
    try:
        import requests as _rq
        r = _rq.post(
            "https://api.buffer.com/graphql",
            json={"query": '{ channel(input: { id: "%s" }) { organizationId } }' % channel_id},
            headers={"Authorization": f"Bearer {buffer_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        org_id = (r.json().get("data", {}).get("channel") or {}).get("organizationId", "")
        if org_id:
            s["buffer_organization_id"] = org_id
            save_settings(s)
        return org_id
    except Exception as e:
        print(f"[{_ts()} BUFFER] _resolve_buffer_org_id failed: {e}")
        return ""


def fetch_buffer_scheduled_texts(buffer_key: str, channel_id: str) -> tuple[list[str], str]:
    """Return (list of scheduled post texts, error_message)."""
    try:
        import requests as _rq
        org_id = _resolve_buffer_org_id(buffer_key, channel_id)
        if not org_id:
            return [], "Could not resolve Buffer organizationId for this channel."
        query = (
            '{ posts(input: { organizationId: "%s",'
            '  filter: { channelIds: ["%s"], status: [scheduled] } }, first: 100) {'
            '  edges { node { text } }'
            '} }' % (org_id, channel_id)
        )
        r = _rq.post(
            "https://api.buffer.com/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {buffer_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        gql_errors = data.get("errors")
        if gql_errors:
            return [], f"Buffer API error: {gql_errors[0].get('message', gql_errors)}"
        edges = data.get("data", {}).get("posts", {}).get("edges", [])
        texts = [e["node"]["text"] for e in edges if e.get("node", {}).get("text")]
        print(f"[{_ts()} BUFFER] fetch_buffer_scheduled_texts: {len(texts)} posts")
        return texts, ""
    except Exception as e:
        print(f"[{_ts()} BUFFER] fetch_buffer_scheduled_texts failed: {e}")
        return [], str(e)


def get_next_available_date(buffer_key, channel_id, post_time, offset_days=0):
    import pytz

    # Try to query Buffer API for the latest scheduled post's dueAt
    last_due_str = ""
    if buffer_key and channel_id:
        try:
            import requests as _rq
            query = """
{ posts(input: { status: scheduled, channelIds: ["%s"], limit: 50 }) {
    edges { node { id dueAt } }
} }""" % channel_id
            r = _rq.post(
                "https://api.buffer.com/graphql",
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {buffer_key}",
                    "Content-Type": "application/json",
                },
                timeout=8,
            )
            edges = r.json().get("data", {}).get("posts", {}).get("edges", [])
            if edges:
                dues = [e["node"]["dueAt"] for e in edges if e.get("node", {}).get("dueAt")]
                if dues:
                    last_due_str = max(dues)
                    print(f"[{_ts()} BUFFER] Latest scheduled post dueAt from API: {last_due_str}")
        except Exception as e:
            print(f"[{_ts()} BUFFER] Buffer API query failed, using settings fallback: {e}")

    # Fall back to settings.json if API didn't return a date
    if not last_due_str:
        settings = load_settings()
        last_due_str = settings.get("last_scheduled_date", "")
        print(f"[{_ts()} BUFFER] Using last_scheduled_date from settings: {last_due_str!r}")

    if last_due_str:
        try:
            last_date = datetime.datetime.fromisoformat(last_due_str.replace("Z", "+00:00"))
            candidate = last_date.date()
            base = candidate if candidate >= datetime.date.today() else datetime.date.today()
        except Exception:
            base = datetime.date.today()
    else:
        base = datetime.date.today()

    print(f"[{_ts()} BUFFER] base={base}, offset_days={offset_days}")
    next_date = base + datetime.timedelta(days=1 + offset_days)
    h, m = map(int, post_time.split(":"))
    local_tz = datetime.datetime.now().astimezone().tzinfo
    dt = datetime.datetime(next_date.year, next_date.month, next_date.day, h, m, tzinfo=local_tz)
    utc_dt = dt.astimezone(pytz.utc)
    print(f"[{_ts()} BUFFER] Next slot: {utc_dt}")
    return utc_dt


def next_available_date_safe(buffer_key: str, channel_id: str, post_time: str,
                             offset_days: int = 0, limit_s: float = 10.0) -> datetime.datetime:
    """get_next_available_date with a hard wall-clock cap. If the Buffer query
    hasn't returned within limit_s seconds (e.g. DNS/TLS stall that the requests
    timeout doesn't bound), fall back to tomorrow + offset_days immediately so
    the export never blocks."""
    fallback = batch_post_datetime(post_time, offset_days)
    box = {"result": fallback}

    def worker():
        try:
            box["result"] = get_next_available_date(
                buffer_key, channel_id, post_time, offset_days
            )
        except Exception:
            box["result"] = fallback

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(limit_s)
    # If still running, abandon it (daemon) and use the fallback already in box.
    return box["result"]


# ── Upload & Buffer ───────────────────────────────────────────────────────────

def upload_video(video_path: Path) -> str:
    import os
    s = load_settings()
    ia_access = s.get("ia_access_key", "").strip()
    ia_secret = s.get("ia_secret_key", "").strip()

    print(f"[UPLOAD] ia_access exists: {bool(ia_access)}, ia_secret exists: {bool(ia_secret)}")

    if not ia_access or not ia_secret:
        raise Exception(
            "Upload failed: Internet Archive not configured. "
            "Open Settings and add your IA Access Key and Secret Key."
        )

    video_path_str = str(video_path)
    filename       = os.path.basename(video_path_str)
    identifier     = f"verdictin60-{filename.replace('.mp4', '').lower().replace(' ', '-')}"
    upload_url     = f"https://s3.us.archive.org/{identifier}/{filename}"
    public_url     = f"https://archive.org/download/{identifier}/{filename}"

    cmd = [
        "curl", "-s", "-X", "PUT", upload_url,
        "-H", f"authorization: LOW {ia_access}:{ia_secret}",
        "-H", "x-archive-auto-make-bucket:1",
        "-H", "x-archive-meta-mediatype:movies",
        "-H", "x-archive-meta-subject:truecrime",
        "-H", "Content-Type: video/mp4",
        "--data-binary", f"@{video_path_str}",
        "--max-time", "600",
    ]
    print(f"[UPLOAD] CMD: {' '.join(cmd[:6])}...")
    print(f"[UPLOAD] file: {video_path_str}  exists: {os.path.exists(video_path_str)}")
    print(f"[UPLOAD] upload_url: {upload_url}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=310)

    print(f"[UPLOAD] returncode: {result.returncode}")
    print(f"[UPLOAD] stdout: {result.stdout[:300]}")
    print(f"[UPLOAD] stderr: {result.stderr[:300]}")

    if result.returncode != 0:
        raise Exception(f"Upload failed: {result.stderr[:200]}")

    # Return the public URL immediately — Archive.org may need extra time before
    # Buffer can read it, so callers should poll/retry before scheduling.
    print(f"[{_ts()} UPLOAD] Upload complete. Returning URL immediately (no polling).")
    return public_url


def schedule_to_buffer(caption: str, video_url: str, channel_id: str,
                       buffer_key: str, post_time: str,
                       due_at_dt: datetime.datetime = None) -> tuple:
    import requests
    if due_at_dt is None:
        due_at = next_post_datetime(post_time)
    else:
        due_at = due_at_dt
    due_str = due_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Use GraphQL variables for text/channelId/dueAt so apostrophes, em dashes,
    # emoji and any other characters in the caption are handled safely without
    # manual escaping. Only video_url is interpolated (a clean archive.org URL).
    mutation = """
mutation CreatePost($text: String!, $channelId: ChannelId!, $dueAt: DateTime) {
  createPost(
    input: {
      text: $text
      channelId: $channelId
      schedulingType: automatic
      mode: customScheduled
      dueAt: $dueAt
      metadata: {
        instagram: {
          type: reel
          shouldShareToFeed: true
        }
      }
      assets: [{ video: { url: "%s" } }]
    }
  ) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}
""" % video_url

    variables = {
        "text": caption,
        "channelId": channel_id,
        "dueAt": due_str,
    }

    r = requests.post(
        "https://api.buffer.com/graphql",
        json={"query": mutation, "variables": variables},
        headers={
            "Authorization": f"Bearer {buffer_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    return r.text, r.json()


def buffer_video_not_ready(message: str) -> bool:
    msg = (message or "").lower()
    return (
        "404" in msg
        or "503" in msg
        or "not accessible" in msg
        or "service unavailable" in msg
        or "verify the url points to a public" in msg
    )


def public_url_http_code(url: str, timeout_s: int = 20) -> str:
    try:
        check = subprocess.run(
            [
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "-L", "--max-time", str(timeout_s), url,
            ],
            capture_output=True, text=True, timeout=timeout_s + 5,
        )
        return check.stdout.strip() or "000"
    except Exception:
        return "000"


def wait_for_public_video_url(url: str, status_cb=None, log_lines=None,
                              max_attempts: int = 8) -> bool:
    """Wait until Archive.org exposes the uploaded file as an HTTP 200 URL."""
    waits = [0, 15, 30, 45, 60, 75, 90, 120]
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            wait_s = waits[min(attempt - 1, len(waits) - 1)]
            if status_cb:
                status_cb(
                    f"⏳  Archive.org still processing — waiting {wait_s}s "
                    f"({attempt}/{max_attempts})"
                )
            time.sleep(wait_s)
        code = public_url_http_code(url)
        if log_lines is not None:
            log_lines.append(f"Archive.org public URL check {attempt}/{max_attempts}: HTTP {code}")
        if code == "200":
            return True
    return False


class UploadPendingError(Exception):
    """Raised when Archive.org upload succeeded but file is not yet HTTP-200 after all polls."""
    def __init__(self, public_url: str):
        self.public_url = public_url
        super().__init__(f"Archive.org is still processing: {public_url}")
