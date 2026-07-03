"""
case_library.py — VerdictIn60 Case Library
SQLite-backed case management with Buffer sync, Pillow thumbnails, and card-grid UI.
"""
import sqlite3, os, io, json, re, shutil, ssl, subprocess, threading, datetime, time, urllib.request, urllib.parse
import tkinter as tk

# Use certifi CA bundle when available so Wikipedia HTTPS works on macOS
try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except Exception:
    _SSL_CTX = None
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ── Colour palette (matches app.py exactly) ───────────────────────────────────
BG          = "#000000"
CRIMSON     = "#940906"
CRIMSON_HOT = "#6b0604"
DARK_CARD   = "#0e0e0e"
WHITE       = "#FFFFFF"
MUTED       = "#555555"
LIGHT_GRAY  = "#888888"
ERROR_RED   = "#ff4444"

STATUS_COLORS = {
    "Draft":     "#555555",
    "Ready":     "#2a6a9a",
    "Scheduled": "#1a6a3a",
    "Published": "#2d8a4e",
    "Failed":    "#cc3333",
    "Archived":  "#444466",
}
STATUS_FG = {
    "Draft":     "#aaaaaa",
    "Ready":     "#6ab0df",
    "Scheduled": "#5acc90",
    "Published": "#5aca8e",
    "Failed":    "#ff8888",
    "Archived":  "#9090bb",
}
ALL_STATUSES = ["Draft", "Ready", "Scheduled", "Published", "Failed", "Archived"]

# Thumbnail dimensions (portrait 9:16)
THUMB_W, THUMB_H = 360, 640
# Card display size (scaled to ≈55%)
CARD_W, CARD_THUMB_H = 200, 356
CARD_H = CARD_THUMB_H + 62      # +text area


# ─────────────────────────────────────────────────────────────────────────────
# Database / business-logic layer
# ─────────────────────────────────────────────────────────────────────────────

class CaseLibrary:
    """Manages case_library.db, Buffer sync, and Pillow thumbnail generation."""

    def __init__(self, base_dir: Path):
        self.base_dir    = Path(base_dir)
        self.db_path     = self.base_dir / "case_library.db"
        self.thumb_dir   = self.base_dir / "library_thumbs"
        self.thumb_dir.mkdir(exist_ok=True)
        self._db_lock    = threading.Lock()
        self._thumb_thread_running = threading.Event()  # prevents duplicate thumbnail threads
        self.on_sync_complete = None   # set by LibraryTab to trigger refresh
        self._log(f"[LIBRARY] CaseLibrary.__init__ starting, base_dir={self.base_dir}")
        self._init_db()
        # Start Buffer sync in background immediately
        self._log("[LIBRARY] launching _sync_buffer_thread daemon thread")
        threading.Thread(target=self._sync_buffer_thread, daemon=True).start()

    # ── DB init ───────────────────────────────────────────────────────────────

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._db_lock, self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_name        TEXT NOT NULL,
                    filename         TEXT    DEFAULT '',
                    status           TEXT    DEFAULT 'Draft',
                    archive_url      TEXT    DEFAULT '',
                    caption          TEXT    DEFAULT '',
                    source_url       TEXT    DEFAULT '',
                    scheduled_date   TEXT    DEFAULT '',
                    buffer_post_id   TEXT    DEFAULT '',
                    thumbnail_path   TEXT    DEFAULT '',
                    processing_log   TEXT    DEFAULT '',
                    import_date      TEXT    DEFAULT '',
                    platform         TEXT    DEFAULT 'Instagram',
                    created_at       TEXT    DEFAULT (datetime('now')),
                    updated_at       TEXT    DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS timeline_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    event_time  TEXT NOT NULL,
                    event_label TEXT NOT NULL,
                    detail      TEXT DEFAULT ''
                );
            """)
            # Migrate older DBs that are missing columns added in later schema versions
            existing = {r[1] for r in c.execute("PRAGMA table_info(cases)").fetchall()}
            for col, defn in [
                ("processing_log", "TEXT DEFAULT ''"),
                ("import_date",    "TEXT DEFAULT ''"),
                ("platform",       "TEXT DEFAULT 'Instagram'"),
            ]:
                if col not in existing:
                    c.execute(f"ALTER TABLE cases ADD COLUMN {col} {defn}")
                    print(f"[LIBRARY] migrated DB: added column {col}", flush=True)

    # ── Settings helpers ──────────────────────────────────────────────────────

    def _load_settings(self) -> dict:
        p = self.base_dir / "settings.json"
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except Exception:
            return {}

    def _save_settings(self, d: dict):
        p = self.base_dir / "settings.json"
        try:
            p.write_text(json.dumps(d, indent=2))
        except Exception:
            pass

    def _resolve_path(self, path: str) -> Path:
        p = Path(path or "")
        return p if p.is_absolute() else (self.base_dir / p)

    def sync_buffer_async(self):
        """Public: refresh scheduled Buffer posts without blocking the UI."""
        threading.Thread(target=self._sync_buffer_thread, daemon=True).start()

    # ── Public write API (called from app.py export hooks) ───────────────────

    def save_case(self, case_name: str, filename: str = "", status: str = "Draft",
                  archive_url: str = "", caption: str = "", scheduled_date: str = "",
                  buffer_post_id: str = "", source_url: str = "",
                  output_path=None) -> int:
        """Upsert a case by (case_name, filename). Returns the row id."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._db_lock, self._conn() as c:
            row = None
            if buffer_post_id:
                row = c.execute(
                    "SELECT id FROM cases WHERE buffer_post_id=?",
                    (buffer_post_id,)
                ).fetchone()
            if row is None:
                row = c.execute(
                    "SELECT id FROM cases WHERE case_name=? AND filename=?",
                    (case_name, filename)
                ).fetchone()
            if row:
                case_id = row["id"]
                c.execute("""
                    UPDATE cases
                       SET status=?, archive_url=?, caption=?, scheduled_date=?,
                           buffer_post_id=?, source_url=?, updated_at=?
                     WHERE id=?
                """, (status, archive_url, caption, scheduled_date,
                      buffer_post_id, source_url, now, case_id))
                self._add_event(c, case_id, now, "Updated", f"status={status}")
            else:
                cur = c.execute("""
                    INSERT INTO cases
                      (case_name, filename, status, archive_url, caption,
                       scheduled_date, buffer_post_id, source_url,
                       import_date, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (case_name, filename, status, archive_url, caption,
                      scheduled_date, buffer_post_id, source_url, now, now, now))
                case_id = cur.lastrowid
                self._add_event(c, case_id, now, "Created", f"status={status}")
        # Generate thumbnail in background (Pillow, not ffmpeg)
        threading.Thread(
            target=self._generate_one_thumbnail,
            args=(case_id, case_name),
            daemon=True
        ).start()
        return case_id

    def update_caption(self, case_id: int, caption: str):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._db_lock, self._conn() as c:
            c.execute("UPDATE cases SET caption=?, updated_at=? WHERE id=?",
                      (caption, now, case_id))
            self._add_event(c, case_id, now, "Caption edited", "")
        if callable(self.on_sync_complete):
            self.on_sync_complete()

    def update_status(self, case_id: int, status: str):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._db_lock, self._conn() as c:
            c.execute("UPDATE cases SET status=?, updated_at=? WHERE id=?",
                      (status, now, case_id))
            self._add_event(c, case_id, now, "Status changed", status)
        if callable(self.on_sync_complete):
            self.on_sync_complete()

    def update_thumbnail(self, case_id: int, path: str):
        with self._db_lock, self._conn() as c:
            c.execute("UPDATE cases SET thumbnail_path=? WHERE id=?", (path, case_id))
        if callable(self.on_sync_complete):
            self.on_sync_complete()

    def delete_case(self, case_id: int):
        with self._db_lock, self._conn() as c:
            row = c.execute("SELECT thumbnail_path FROM cases WHERE id=?",
                            (case_id,)).fetchone()
            if row and row["thumbnail_path"]:
                try:
                    self._resolve_path(row["thumbnail_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            c.execute("DELETE FROM cases WHERE id=?", (case_id,))
        if callable(self.on_sync_complete):
            self.on_sync_complete()

    # ── Public read API ───────────────────────────────────────────────────────

    def get_all(self, status_filter: str = "All", search: str = "") -> list:
        q, params = "SELECT * FROM cases", []
        conds = []
        if status_filter == "Active":
            conds.append("status IN ('Scheduled','Published')")
        elif status_filter != "All":
            conds.append("status=?")
            params.append(status_filter)
        if search:
            s = f"%{search}%"
            conds.append(
                "(case_name LIKE ? OR caption LIKE ? "
                "OR source_url LIKE ? OR scheduled_date LIKE ?)"
            )
            params += [s, s, s, s]
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY updated_at DESC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, params).fetchall()]

    def get_by_id(self, case_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                return None
            case = dict(row)
            case["timeline"] = [
                dict(e) for e in c.execute(
                    "SELECT * FROM timeline_events WHERE case_id=? ORDER BY event_time DESC",
                    (case_id,)
                ).fetchall()
            ]
            return case

    # ── Timeline helper ───────────────────────────────────────────────────────

    def _add_event(self, conn, case_id: int, ts: str, label: str, detail: str):
        conn.execute(
            "INSERT INTO timeline_events (case_id, event_time, event_label, detail)"
            " VALUES (?,?,?,?)",
            (case_id, ts, label, detail or "")
        )

    # ── Buffer sync ───────────────────────────────────────────────────────────

    def _log(self, msg: str):
        """Write to stdout and append to library.log for GUI-launch debugging."""
        print(msg, flush=True)
        try:
            log_path = self.base_dir / "library.log"
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    def _sync_buffer_thread(self):
        try:
            self._log("[LIBRARY] starting _sync_buffer_thread...")
            s     = self._load_settings()
            bkey  = (s.get("buffer_key") or "").strip()
            bcid  = (s.get("buffer_channel_id") or "").strip()
            self._log(f"[LIBRARY] key present={bool(bkey)}, channel_id present={bool(bcid)}")
            if not bkey or not bcid:
                self._log("[LIBRARY] _sync_buffer_thread: missing credentials, aborting")
                return

            posts = self._fetch_buffer_posts(bkey, bcid)
            if not posts:
                self._log("[LIBRARY] _sync_buffer_thread: no posts returned")
                return
            dues = [e["node"]["dueAt"] for e in posts
                    if e.get("node", {}).get("dueAt")]
            if not dues:
                return
            latest_due = max(dues)
            self._log(f"[LIBRARY] Buffer sync/upsert: {len(posts)} posts, latest={latest_due}")
            now = datetime.datetime.now().isoformat(timespec="seconds")
            with self._db_lock, self._conn() as c:
                for edge in posts:
                    node = edge.get("node", {})
                    self._insert_buffer_node(c, node, now)

            s["last_scheduled_date"] = latest_due
            self._save_settings(s)

            if callable(self.on_sync_complete):
                self.on_sync_complete()
            # Generate thumbnails for newly synced cases (flag prevents duplicate threads)
            threading.Thread(target=self._generate_all_thumbnails, daemon=True).start()
        except Exception as e:
            import traceback
            self._log(f"[LIBRARY] _sync_buffer_thread EXCEPTION: {e}\n{traceback.format_exc()}")

    def _get_org_id(self, bkey: str, bcid: str) -> str:
        """Resolve organizationId for the channel; cache in settings.json."""
        s = self._load_settings()
        cached = (s.get("buffer_organization_id") or "").strip()
        if cached:
            self._log(f"[LIBRARY] org_id from cache: {cached!r}")
            return cached
        self._log("[LIBRARY] fetching org_id from Buffer API...")
        try:
            import requests as _rq
            r = _rq.post(
                "https://api.buffer.com/graphql",
                json={"query": '{ channel(input: { id: "%s" }) { organizationId } }' % bcid},
                headers={"Authorization": f"Bearer {bkey}",
                         "Content-Type": "application/json"},
                timeout=10,
            )
            self._log(f"[LIBRARY] org_id response HTTP {r.status_code}: {r.text[:200]}")
            org_id = (r.json().get("data", {}).get("channel") or {}).get("organizationId", "")
            if org_id:
                s["buffer_organization_id"] = org_id
                self._save_settings(s)
            return org_id
        except Exception as e:
            import traceback
            self._log(f"[LIBRARY] Could not resolve organizationId: {e}\n{traceback.format_exc()}")
            return ""

    def _fetch_buffer_posts(self, bkey: str, bcid: str) -> list:
        self._log("[LIBRARY] starting _fetch_buffer_posts...")
        org_id = self._get_org_id(bkey, bcid)
        self._log(f"[LIBRARY] org_id resolved: {org_id!r}")
        if not org_id:
            self._log("[LIBRARY] Buffer sync skipped: could not resolve organizationId")
            return []
        query = (
            '{ posts(input: { organizationId: "%s",'
            '  filter: { channelIds: ["%s"], status: [scheduled] } }, first: 100) {'
            '  edges { node { id dueAt text } }'
            '} }' % (org_id, bcid)
        )
        self._log("[LIBRARY] firing requests.post to Buffer GraphQL...")
        try:
            import requests as _rq
            r = _rq.post(
                "https://api.buffer.com/graphql",
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {bkey}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            self._log(f"[LIBRARY] Buffer GraphQL HTTP {r.status_code}")
            if not r.ok:
                self._log(f"[LIBRARY] Buffer fetch HTTP {r.status_code}: {r.text[:400]}")
                return []
            data = r.json()
            if "errors" in data:
                self._log(f"[LIBRARY] Buffer GraphQL errors: {data['errors']}")
                return []
            edges = data.get("data", {}).get("posts", {}).get("edges", [])
            self._log(f"[LIBRARY] Buffer returned {len(edges)} edges")
            return edges
        except Exception as e:
            import traceback
            self._log(f"[LIBRARY] Buffer fetch failed: {e}\n{traceback.format_exc()}")
            return []

    def _insert_buffer_node(self, conn, node: dict, now: str):
        bid       = node.get("id", "")
        due_at    = node.get("dueAt", "")
        text      = node.get("text", "")
        case_name = _extract_case_name(text)
        if not case_name:
            return
        filename  = _make_filename(case_name)
        sched_date = due_at or ""

        row = None
        if bid:
            row = conn.execute(
                "SELECT id, filename, archive_url, thumbnail_path, source_url FROM cases WHERE buffer_post_id=?",
                (bid,)
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, filename, archive_url, thumbnail_path, source_url FROM cases "
                "WHERE case_name=? AND scheduled_date=?",
                (case_name, sched_date)
            ).fetchone()

        if row:
            case_id = row["id"]
            keep_filename = row["filename"] or filename
            conn.execute("""
                UPDATE cases
                   SET case_name=?, filename=?, status='Scheduled',
                       caption=?, scheduled_date=?, buffer_post_id=?,
                       updated_at=?
                 WHERE id=?
            """, (case_name, keep_filename, text, sched_date, bid, now, case_id))
            self._add_event(conn, case_id, now, "Synced from Buffer", f"dueAt={due_at}")
        else:
            conn.execute("""
                INSERT INTO cases
                  (case_name, filename, status, caption, scheduled_date,
                   buffer_post_id, import_date, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (case_name, filename, "Scheduled", text, sched_date,
                  bid, now, now, now))
            case_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._add_event(conn, case_id, now, "Imported from Buffer",
                            f"dueAt={due_at}")

    # ── Thumbnail generation ──────────────────────────────────────────────────

    def _generate_all_thumbnails(self):
        if self._thumb_thread_running.is_set():
            self._log("[LIBRARY] _generate_all_thumbnails already running, skipping duplicate")
            return
        self._thumb_thread_running.set()
        try:
            self._log("[LIBRARY] starting _generate_all_thumbnails...")
            with self._conn() as c:
                rows = c.execute(
                    "SELECT id, case_name, filename, caption, scheduled_date FROM cases "
                    "WHERE thumbnail_path='' OR thumbnail_path IS NULL"
                ).fetchall()
            self._log(f"[LIBRARY] found {len(rows)} cases missing thumbnails")
            for i, row in enumerate(rows):
                self._log(f"[LIBRARY] processing case {i+1}/{len(rows)}: id={row['id']} name={row['case_name']!r:.50}")
                if i > 0:
                    time.sleep(2)   # avoid Wikipedia 429 rate limiting
                caption = (row["caption"] or "").strip()
                fn      = (row["filename"] or "").strip()
                if caption:
                    wiki_name = _extract_case_name(caption)
                elif fn.endswith(".mp4"):
                    stem  = fn[:-4].replace("-", " ").strip()
                    words = stem.split()
                    wiki_name = stem if len(words) <= 5 else row["case_name"]
                else:
                    wiki_name = row["case_name"]
                self._log(f"[LIBRARY] generating thumbnail for: {wiki_name!r}")
                self._generate_one_thumbnail(
                    row["id"], wiki_name,
                    caption=row["caption"] or "",
                    scheduled_date=row["scheduled_date"] or "",
                )
        except Exception as e:
            import traceback
            self._log(f"[LIBRARY] _generate_all_thumbnails EXCEPTION: {e}\n{traceback.format_exc()}")
        finally:
            self._thumb_thread_running.clear()

    def _generate_one_thumbnail(self, case_id: int, case_name: str,
                                caption: str = "", scheduled_date: str = ""):
        """Build a 360x640 JPEG thumbnail.

        With Wikipedia photo: photo + dark gradient overlays + bars + logo.
        Without Wikipedia photo: cinematic fallback — dark radial gradient,
        film-grain noise, atmospheric key-phrase watermark, crimson bars.
        Always saves a JPEG regardless of what fails.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return
        W, H = THUMB_W, THUMB_H

        # If caller didn't pass caption/date, look them up from the DB
        if not caption or not scheduled_date:
            with self._conn() as c:
                row = c.execute(
                    "SELECT caption, scheduled_date FROM cases WHERE id=?",
                    (case_id,)
                ).fetchone()
                if row:
                    caption        = caption        or (row["caption"]        or "")
                    scheduled_date = scheduled_date or (row["scheduled_date"] or "")

        try:
            photo = self._fetch_wiki_photo(case_name)
        except Exception:
            photo = None

        if photo:
            img = self._render_photo_thumbnail(photo, W, H)
        else:
            img = self._render_fallback_thumbnail(case_name, caption, W, H)

        draw = ImageDraw.Draw(img)

        # ── Top bar: thin crimson line + "VERDICTIN60" left, date right ───────
        draw.rectangle([(0, 0), (W, 3)], fill=(148, 9, 6))
        font_xs = _pil_font(11)
        draw.text((10, 7), "VERDICTIN60", font=font_xs, fill=(255, 255, 255))
        if scheduled_date:
            try:
                dt   = datetime.datetime.fromisoformat(
                    scheduled_date.split("Z")[0].strip())
                dfmt = dt.strftime("%b %-d, %Y")
            except Exception:
                dfmt = scheduled_date[:10]
            if font_xs:
                bb = draw.textbbox((0, 0), dfmt, font=font_xs)
                draw.text((W - (bb[2] - bb[0]) - 10, 7), dfmt,
                          font=font_xs, fill=(200, 200, 200))

        # ── Bottom bar: solid crimson + case name in bold white ───────────────
        bar_h  = 80
        bar_y  = H - bar_h
        draw.rectangle([(0, bar_y), (W, H)], fill=(148, 9, 6))

        font_name  = _pil_font(24)
        font_name2 = _pil_font(20)
        name_upper = case_name.upper()
        lines = _wrap_text(draw, name_upper, font_name, W - 20)
        # If wrapping produces > 2 lines, switch to smaller font
        if len(lines) > 2:
            lines = _wrap_text(draw, name_upper, font_name2, W - 20)
            font_use = font_name2
        else:
            font_use = font_name
        # Vertically centre text in the bar
        line_h  = (draw.textbbox((0, 0), "Ag", font=font_use)[3] + 3)
        total_h = line_h * min(len(lines), 3)
        y_name  = bar_y + (bar_h - total_h) // 2
        for line in lines[:3]:
            bb = draw.textbbox((0, 0), line, font=font_use)
            draw.text(((W - (bb[2] - bb[0])) // 2, y_name),
                      line, font=font_use, fill=(255, 255, 255))
            y_name += line_h

        # ── Logo top-left at 40 % opacity ─────────────────────────────────────
        logo_path = self.base_dir / "assets" / "logo.png"
        if logo_path.exists():
            try:
                logo = Image.open(logo_path).convert("RGBA")
                logo.thumbnail((110, 52), Image.LANCZOS)
                r2, g2, b2, a2 = logo.split()
                a2 = a2.point(lambda x: int(x * 0.40))
                logo.putalpha(a2)
                base_rgba = img.convert("RGBA")
                base_rgba.paste(logo, (10, 14), logo)
                img = base_rgba.convert("RGB")
            except Exception:
                pass

        # ── Save ──────────────────────────────────────────────────────────────
        dest = self.thumb_dir / f"case_{case_id}.jpg"
        img.save(str(dest), "JPEG", quality=87)
        with self._db_lock, self._conn() as c:
            c.execute("UPDATE cases SET thumbnail_path=? WHERE id=?",
                      (str(dest.resolve()), case_id))
        if callable(self.on_sync_complete):
            self.on_sync_complete()

    # ── Photo thumbnail (Wikipedia image available) ────────────────────────────

    def _render_photo_thumbnail(self, photo, W: int, H: int):
        from PIL import Image, ImageDraw
        img   = Image.new("RGB", (W, H), (0, 0, 0))
        ratio = W / photo.width
        ph    = int(photo.height * ratio)
        photo = photo.resize((W, ph), Image.LANCZOS)
        img.paste(photo, (0, max(0, (H - ph) // 2)))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od      = ImageDraw.Draw(overlay)
        bot_start = int(H * 0.55)
        for y in range(bot_start, H):
            a = int(230 * (y - bot_start) / (H - bot_start))
            od.line([(0, y), (W - 1, y)], fill=(0, 0, 0, a))
        top_end = int(H * 0.22)
        for y in range(0, top_end):
            a = int(170 * (top_end - y) / top_end)
            od.line([(0, y), (W - 1, y)], fill=(0, 0, 0, a))
        return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # ── Cinematic fallback thumbnail (no Wikipedia photo) ─────────────────────

    def _render_fallback_thumbnail(self, case_name: str, caption: str,
                                   W: int, H: int):
        """Dark atmospheric thumbnail built entirely with Pillow."""
        import math, random
        from PIL import Image, ImageDraw

        # ── Dark radial gradient background ───────────────────────────────────
        img  = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy  = W // 2, H // 2
        max_r   = math.hypot(cx, cy)
        for y in range(H):
            for x in range(W):
                d = math.hypot(x - cx, y - cy) / max_r   # 0 at centre → 1 at corner
                # Centre: (120,8,6)  Edge: (28,2,2)
                v = int(28 + 92 * max(0.0, 1.0 - d * 1.1))
                draw.point((x, y), fill=(v, max(0, v//14), max(0, v//16)))

        # ── Film-grain noise overlay ───────────────────────────────────────────
        rng   = random.Random(hash(case_name) & 0xFFFFFFFF)
        noise = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        nd    = ImageDraw.Draw(noise)
        for _ in range(W * H // 4):
            nx = rng.randint(0, W - 1)
            ny = rng.randint(0, H - 1)
            bv = rng.randint(20, 70)
            na = rng.randint(8, 28)
            nd.point((nx, ny), fill=(bv, bv, bv, na))
        img = Image.alpha_composite(img.convert("RGBA"), noise).convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── Atmospheric key phrase watermark (visible but faded) ──────────────
        phrase = _extract_key_phrase(caption, case_name)
        if phrase:
            wm_lay  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            wm_draw = ImageDraw.Draw(wm_lay)
            wm_font = _pil_font(46)
            wm_lines = _wrap_text(wm_draw, phrase.upper(), wm_font, W - 40)
            wm_lh    = 52
            wm_total = wm_lh * len(wm_lines)
            wm_y     = (H - wm_total) // 2 - 30
            for line in wm_lines:
                bb  = wm_draw.textbbox((0, 0), line, font=wm_font)
                lw  = bb[2] - bb[0]
                wm_draw.text(((W - lw) // 2, wm_y), line,
                             font=wm_font, fill=(220, 60, 40, 140))
                wm_y += wm_lh
            img = Image.alpha_composite(img.convert("RGBA"), wm_lay).convert("RGB")
            draw = ImageDraw.Draw(img)

        # ── Top bar: thin crimson line + branding ──────────────────────────────
        BAR_H = 38
        draw.rectangle([0, 0, W, BAR_H], fill=(10, 0, 0))
        draw.rectangle([0, BAR_H - 2, W, BAR_H], fill=(148, 9, 6))
        top_font = _pil_font(14)
        draw.text((10, 10), "VERDICTIN60", font=top_font, fill=(200, 200, 200))

        # ── Bottom bar: solid crimson + case name ─────────────────────────────
        BOT_H = 72
        draw.rectangle([0, H - BOT_H, W, H], fill=(148, 9, 6))
        draw.rectangle([0, H - BOT_H, W, H - BOT_H + 2], fill=(200, 20, 10))
        name_font  = _pil_font(22)
        name_lines = _wrap_text(draw, case_name.upper(), name_font, W - 20)
        ny = H - BOT_H + 12
        for line in name_lines[:2]:
            bb = draw.textbbox((0, 0), line, font=name_font)
            lw = bb[2] - bb[0]
            draw.text(((W - lw) // 2, ny), line, font=name_font, fill=(255, 255, 255))
            ny += 26

        return img

    def _fetch_wiki_photo(self, case_name: str):
        try:
            from PIL import Image
        except ImportError:
            return None
        try:
            enc = urllib.parse.quote(case_name.replace(" ", "_"))
            ua  = "VerdictIn60/1.0 (contact@verdictin60.com)"
            req = urllib.request.Request(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{enc}",
                headers={"User-Agent": ua}
            )
            kw = {"context": _SSL_CTX} if _SSL_CTX else {}
            with urllib.request.urlopen(req, timeout=10, **kw) as r:
                data = json.loads(r.read())
            photo_url = data.get("thumbnail", {}).get("source", "")
            if not photo_url:
                return None
            req2 = urllib.request.Request(
                photo_url,
                headers={"User-Agent": ua}
            )
            with urllib.request.urlopen(req2, timeout=10, **kw) as r2:
                return Image.open(io.BytesIO(r2.read())).convert("RGB")
        except Exception as e:
            print(f"[LIBRARY] Wiki photo failed for {case_name!r}: {e}", flush=True)
            return None

    def regenerate_thumbnail(self, case_id: int, case_name: str):
        """Public: regenerate thumbnail on demand (called from detail dialog)."""
        # Remove old file
        with self._db_lock, self._conn() as c:
            row = c.execute("SELECT thumbnail_path FROM cases WHERE id=?",
                            (case_id,)).fetchone()
            if row and row["thumbnail_path"]:
                try:
                    self._resolve_path(row["thumbnail_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            c.execute("UPDATE cases SET thumbnail_path='' WHERE id=?", (case_id,))
        threading.Thread(
            target=self._generate_one_thumbnail,
            args=(case_id, case_name),
            daemon=True
        ).start()


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers (no self needed)
# ─────────────────────────────────────────────────────────────────────────────

# High-impact words and short phrases that make good atmospheric watermarks
_CHILLING_PATTERNS = [
    # Victim counts
    (re.compile(r'killed?\s+(\d+\+?\s*(?:people|victims|women|men|children|patients|prisoners))',
                re.I), lambda m: m.group(0)),
    (re.compile(r'(\d+\+?\s*(?:murders?|killings?|deaths?|victims?))', re.I),
     lambda m: m.group(0)),
    (re.compile(r'murdered?\s+(?:at\s+least\s+)?(\d+)', re.I),
     lambda m: m.group(0)),
    # Methods / descriptors — direct extraction
    (re.compile(
        r'\b(cannibalism|cannibalistic|poisoned?|strangulation|strangled?|'
        r'dismembered?|decapitated?|torture[ds]?|executed?|abducted?|'
        r'serial\s+killer|mass\s+murderer|child\s+killer|cannibal|'
        r'unidentified|never\s+caught|escaped\s+justice|'
        r'ate\s+his\s+victims|drank\s+blood|kept\s+trophies|'
        r'confessed\s+to\s+\d+|convicted\s+of\s+\d+|'
        r'100\s+years?\s+old|oldest|youngest|most\s+prolific|'
        r'never\s+identified|cold\s+case|unsolved)\b',
        re.I), lambda m: m.group(0)),
]


def _extract_key_phrase(caption: str, case_name: str) -> str:
    """Extract a short atmospheric phrase from the caption for the watermark.

    Tries chilling-word patterns first, then falls back to a striking
    2-5 word fragment from the first non-boilerplate sentence.
    Returns empty string if nothing useful found.
    """
    if not caption:
        return ""

    # Strip hashtag section (everything after the first # cluster)
    body = re.split(r'\n+#', caption)[0].strip()

    # Try each pattern in priority order
    for pattern, extractor in _CHILLING_PATTERNS:
        m = pattern.search(body)
        if m:
            phrase = extractor(m).strip()
            if 3 <= len(phrase) <= 40:
                return phrase

    # Fallback: find the most "striking" short clause.
    # Look for sentences containing numbers or strong verbs.
    sentences = re.split(r'[.!?\n]+', body)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 10 or len(sent) > 120:
            continue
        # Skip opener lines that are the VerdictIn60 header or case name
        if case_name.lower()[:12] in sent.lower() or "verdictin60" in sent.lower():
            continue
        # Prefer sentences with a number or a strong keyword
        if re.search(r'\d+|killed|murdered|convicted|sentenced|died|escaped|'
                     r'guilty|arrested|abducted', sent, re.I):
            # Trim to ≤6 words
            words = sent.split()[:6]
            return " ".join(words)

    return ""


def _extract_case_name(text: str) -> str:
    """Extract a person's name from a Buffer post caption.

    Handles two real caption formats observed in production:
      1. 'VerdictIn60: Firstname Lastname\\n\\nBody...'  → 'Firstname Lastname'
      2. 'A sentence about Firstname Lastname...'        → first proper noun pair found
    """
    text = text.strip()

    # Format 1 — explicit header like "VerdictIn60: Josef Schütz"
    m = re.match(r'(?:VerdictIn60|V60)\s*[:\-]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        # Strip leftover trailing punctuation / emoji
        name = re.sub(r'[…\*]+$', '', name).strip()
        if name:
            return name

    # Format 2 — hashtag like #CassandraFeuerstein → split CamelCase into words
    for tag in re.findall(r'#([A-Z][a-zA-Z]{2,})', text):
        words = re.findall(r'[A-Z][a-z]+', tag)
        if 2 <= len(words) <= 4:   # looks like a person name, not a generic tag
            return ' '.join(words)

    # Format 3 — first occurrence of two+ consecutive Title Case words in the body
    # (skips common non-name starters like "In 2015," "A college", titles like "Officer")
    _skip = re.compile(
        r'^(In|On|At|A|An|The|After|Before|When|During|From|Officer|Detective'
        r'|Sergeant|Deputy|Chief|Doctor|Dr|Mr|Mrs|Ms|Judge|Senator|Father)\b'
    )
    for m in re.finditer(
        r'\b([A-Z][a-z]{1,14}(?:\s+[A-Z][a-z]{1,14}){1,3})\b', text
    ):
        candidate = m.group(1)
        if not _skip.match(candidate):
            return candidate

    # Fallback — first line, stripped of hashtags and emoji
    first = text.split('\n')[0]
    first = re.sub(r'#\w+', '', first)
    first = re.sub(r'[^\x00-\x7F]+', '', first)
    return first.strip()[:80]


def _make_filename(case_name: str) -> str:
    words = re.findall(r'[a-zA-Z0-9]+', case_name)
    return "-".join(w.capitalize() for w in words) + ".mp4" if words else "Untitled.mp4"


def _pil_font(size: int):
    try:
        from PIL import ImageFont
        for path in (
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ):
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        try:
            from PIL import ImageFont
            return ImageFont.load_default()
        except Exception:
            return None


def _wrap_text(draw, text: str, font, max_width: int) -> list:
    try:
        words = text.split()
        lines, cur = [], ""
        for word in words:
            test = (cur + " " + word).strip()
            bb   = draw.textbbox((0, 0), test, font=font)
            if (bb[2] - bb[0]) <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines
    except Exception:
        return [text]


# ─────────────────────────────────────────────────────────────────────────────
# Card-grid tab widget
# ─────────────────────────────────────────────────────────────────────────────

class LibraryTab:
    def __init__(self, parent: tk.Frame, library: CaseLibrary):
        print("[LIBRARY] LibraryTab.__init__ starting", flush=True)
        self.parent  = parent
        self.library = library

        self._filter     = "Active"
        self._search_str = ""
        self._search_job = None
        self._cards      = []       # list of (case_id, card_frame)
        self._thumb_refs = {}       # case_id → PhotoImage (keep alive)
        self._col_count  = 3

        # Wire library callbacks so UI auto-refreshes after sync / thumbnail
        self.library.on_sync_complete = lambda: parent.after(0, self.refresh)

        self._build_ui()
        self.refresh()

        # Generate thumbnails for any cases that don't have one yet
        print("[LIBRARY] LibraryTab: launching _generate_all_thumbnails thread", flush=True)
        threading.Thread(
            target=self.library._generate_all_thumbnails, daemon=True
        ).start()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        PAD = 20

        # ── Filter bar ────────────────────────────────────────────────────────
        fb = tk.Frame(self.parent, bg=BG)
        fb.pack(fill="x", padx=PAD, pady=(14, 0))
        self._filter_btns: dict[str, tk.Label] = {}
        for label in ["Active", "Scheduled", "Published", "All"]:
            btn = tk.Label(fb, text=label, bg="#111111", fg=MUTED,
                           font=("Helvetica", 9, "bold"),
                           padx=11, pady=6, cursor="hand2")
            btn.pack(side="left", padx=(0, 3))
            btn.bind("<Button-1>", lambda e, s=label: self._set_filter(s))
            _hover_label(btn, "#111111", "#1a1a1a", MUTED, LIGHT_GRAY)
            self._filter_btns[label] = btn
        self._filter_btns["Active"].config(bg=CRIMSON, fg=WHITE)

        # ── Search ────────────────────────────────────────────────────────────
        sw = tk.Frame(self.parent, bg="#111111",
                      highlightthickness=1, highlightbackground="#2a2a2a")
        sw.pack(fill="x", padx=PAD, pady=(8, 0))
        tk.Label(sw, text="⌕", bg="#111111", fg=LIGHT_GRAY,
                 font=("Helvetica", 14)).pack(side="left", padx=(10, 3))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        tk.Entry(sw, textvariable=self._search_var,
                 bg="#111111", fg=WHITE, insertbackground=WHITE,
                 font=("Helvetica", 11), bd=0, relief="flat",
                 highlightthickness=0).pack(fill="x", side="left",
                 expand=True, padx=(0, 10), pady=8)

        # ── Scrollable card grid ──────────────────────────────────────────────
        go = tk.Frame(self.parent, bg=BG)
        go.pack(fill="both", expand=True, padx=PAD, pady=(10, 8))

        self._canvas = tk.Canvas(go, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(go, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._grid = tk.Frame(self._canvas, bg=BG)
        self._win  = self._canvas.create_window((0, 0), window=self._grid, anchor="nw")
        self._grid.bind("<Configure>",
                        lambda e: self._canvas.configure(
                            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<Enter>",
                          lambda e: self._canvas.bind_all("<MouseWheel>", self._scroll))
        self._canvas.bind("<Leave>",
                          lambda e: self._canvas.unbind_all("<MouseWheel>"))

    def _scroll(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _on_canvas_resize(self, e):
        self._canvas.itemconfig(self._win, width=e.width)
        cols = max(1, e.width // (CARD_W + 12))
        if cols != self._col_count:
            self._col_count = cols
            self._reflow()

    # ── Filter / search ───────────────────────────────────────────────────────

    def _set_filter(self, s: str):
        self._filter = s
        for k, btn in self._filter_btns.items():
            btn.config(bg=CRIMSON if k == s else "#111111",
                       fg=WHITE   if k == s else MUTED)
        self.refresh()

    def _on_search(self, *_):
        if self._search_job:
            self.parent.after_cancel(self._search_job)
        self._search_job = self.parent.after(200, self._do_search)

    def _do_search(self):
        self._search_str = self._search_var.get().strip()
        self.refresh()

    # ── Card grid ─────────────────────────────────────────────────────────────

    def refresh(self):
        cases = self.library.get_all(self._filter, self._search_str)
        for w in self._grid.winfo_children():
            w.destroy()
        self._cards.clear()
        self._thumb_refs.clear()

        if not cases:
            tk.Label(self._grid,
                     text="No cases yet.\n\nExport a reel and it will appear here automatically.",
                     font=("Helvetica", 11), fg="#2a2a2a", bg=BG,
                     justify="center").grid(row=0, column=0, pady=80, padx=80)
            return

        for case in cases:
            card = self._make_card(case)
            self._cards.append((case["id"], card))
        self._reflow()

    def _reflow(self):
        for i, (_, card) in enumerate(self._cards):
            card.grid(row=i // self._col_count,
                      column=i % self._col_count,
                      padx=6, pady=6, sticky="nw")

    def _make_card(self, case: dict) -> tk.Frame:
        cid    = case["id"]
        name   = case["case_name"] or "Untitled"
        status = case.get("status") or "Draft"
        sched  = case.get("scheduled_date") or ""
        thumbp = case.get("thumbnail_path") or ""

        card = tk.Frame(self._grid, bg=DARK_CARD,
                        width=CARD_W, height=CARD_H,
                        highlightthickness=1, highlightbackground="#2a2a2a",
                        cursor="hand2")
        card.pack_propagate(False)
        card.grid_propagate(False)

        # Thumbnail area (portrait 9:16)
        tf = tk.Frame(card, bg="#0a0a0a", width=CARD_W, height=CARD_THUMB_H)
        tf.pack(fill="x")
        tf.pack_propagate(False)
        tl = tk.Label(tf, bg="#0a0a0a")
        tl.place(relwidth=1.0, relheight=1.0)

        thumb_path = self.library._resolve_path(thumbp) if thumbp else Path("")
        if thumbp and thumb_path.exists():
            self._load_thumb(tl, str(thumb_path), cid)
        else:
            # Placeholder with crimson stripe
            pl = tk.Frame(tf, bg=CRIMSON, width=3)
            pl.place(x=0, y=0, relheight=1.0)
            tk.Label(tf, text="▶", fg="#1e1e1e", bg="#0a0a0a",
                     font=("Helvetica", 26, "bold")).place(
                         relx=0.5, rely=0.5, anchor="center")

        # Text body
        body = tk.Frame(card, bg=DARK_CARD)
        body.pack(fill="both", expand=True, padx=8, pady=(5, 4))

        disp = (name[:22] + "…") if len(name) > 22 else name
        tk.Label(body, text=disp, bg=DARK_CARD, fg=WHITE,
                 font=("Helvetica", 10, "bold"), anchor="w").pack(anchor="w")

        badge_row = tk.Frame(body, bg=DARK_CARD)
        badge_row.pack(anchor="w", pady=(2, 0))
        tk.Label(badge_row, text=f"● {status}", bg=DARK_CARD,
                 fg=STATUS_FG.get(status, LIGHT_GRAY),
                 font=("Helvetica", 8, "bold")).pack(side="left")

        if sched:
            try:
                dt  = datetime.datetime.fromisoformat(sched.split("Z")[0].strip())
                sfmt = dt.strftime("%b %-d, %Y")
            except Exception:
                sfmt = sched[:10]
            tk.Label(body, text=sfmt, bg=DARK_CARD, fg="#3a3a3a",
                     font=("Helvetica", 8)).pack(anchor="w", pady=(1, 0))

        # Hover + click (bind recursively so children don't swallow events)
        def _enter(_): card.config(highlightbackground=CRIMSON)
        def _leave(_): card.config(highlightbackground="#2a2a2a")
        self._bind_card(card, cid, _enter, _leave)
        return card

    def _bind_card(self, widget, cid, enter_cb, leave_cb):
        widget.bind("<Enter>",    enter_cb)
        widget.bind("<Leave>",    leave_cb)
        widget.bind("<Button-1>", lambda e, c=cid: self._open_detail(c))
        widget.bind("<Button-2>", lambda e, c=cid: self._ctx_menu(e, c))
        widget.bind("<Button-3>", lambda e, c=cid: self._ctx_menu(e, c))
        for child in widget.winfo_children():
            self._bind_card(child, cid, enter_cb, leave_cb)

    def _load_thumb(self, lbl: tk.Label, path: str, cid: int):
        try:
            from PIL import Image, ImageTk
            resolved = self.library._resolve_path(path)
            self.library._log(f"[LIBRARY] _load_thumb cid={cid} path={resolved} exists={resolved.exists()}")
            img   = Image.open(resolved)
            img.thumbnail((CARD_W, CARD_THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._thumb_refs[cid] = photo
            lbl.config(image=photo, bg="#0a0a0a")
            self.library._log(f"[LIBRARY] _load_thumb cid={cid} OK")
        except Exception as e:
            import traceback
            self.library._log(f"[LIBRARY] _load_thumb cid={cid} FAILED: {e}\n{traceback.format_exc()}")

    # ── Context menu ──────────────────────────────────────────────────────────

    def _ctx_menu(self, event, cid: int):
        m = tk.Menu(self.parent, tearoff=0, bg="#1a1a1a", fg=WHITE,
                    activebackground=CRIMSON, activeforeground=WHITE,
                    bd=0, relief="flat", font=("Helvetica", 10))
        m.add_command(label="Open Case",
                      command=lambda: self._open_detail(cid))
        m.add_command(label="Copy Caption",
                      command=lambda: self._copy_caption(cid))
        m.add_command(label="Open Archive.org",
                      command=lambda: self._open_archive(cid))
        m.add_separator()
        m.add_command(label="Delete Case",
                      foreground=ERROR_RED,
                      command=lambda: self._delete_case(cid))
        m.tk_popup(event.x_root, event.y_root)

    def _copy_caption(self, cid: int):
        case = self.library.get_by_id(cid)
        if case and case.get("caption"):
            self.parent.clipboard_clear()
            self.parent.clipboard_append(case["caption"])

    def _open_archive(self, cid: int):
        case = self.library.get_by_id(cid)
        if case and case.get("archive_url"):
            subprocess.Popen(["open", case["archive_url"]])

    def _delete_case(self, cid: int):
        if messagebox.askyesno(
            "Delete Case",
            "Remove this case from the library?\n(Video file on disk is not deleted.)",
            icon="warning"
        ):
            self.library.delete_case(cid)
            self.refresh()

    def _open_detail(self, cid: int):
        case = self.library.get_by_id(cid)
        if case:
            CaseDetailDialog(
                self.parent.winfo_toplevel(), case, self.library
            ).on_close = self.refresh


# ─────────────────────────────────────────────────────────────────────────────
# Case detail dialog
# ─────────────────────────────────────────────────────────────────────────────

class CaseDetailDialog(tk.Toplevel):
    def __init__(self, parent, case: dict, library: CaseLibrary):
        super().__init__(parent)
        self.case    = case
        self.library = library
        self.on_close    = None
        self._thumb_ref  = None

        self.title("CASE DETAIL — VERDICTIN60")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(680, 560)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 740, 840
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        if callable(self.on_close):
            self.on_close()
        self.destroy()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        case = self.case
        PAD  = 28

        tk.Frame(self, bg=CRIMSON, height=3).pack(fill="x")

        # Scrollable outer
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        cvs = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb  = ttk.Scrollbar(outer, orient="vertical", command=cvs.yview)
        cvs.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cvs.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cvs, bg=BG)
        win   = cvs.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.bind("<Configure>", lambda e: cvs.itemconfig(win, width=e.width))
        cvs.bind("<Enter>",
                 lambda e: cvs.bind_all(
                     "<MouseWheel>",
                     lambda ev: cvs.yview_scroll(int(-1*(ev.delta/120)), "units")))
        cvs.bind("<Leave>", lambda e: cvs.unbind_all("<MouseWheel>"))

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(inner, bg=BG)
        hdr.pack(fill="x", padx=PAD, pady=(22, 0))
        status = case.get("status") or "Draft"
        tk.Label(hdr, text=case["case_name"] or "Untitled",
                 bg=BG, fg=WHITE, font=("Helvetica", 17, "bold"),
                 anchor="w", wraplength=560, justify="left").pack(
                 side="left", fill="x", expand=True)
        tk.Label(hdr, text=f"● {status}", bg=BG,
                 fg=STATUS_FG.get(status, LIGHT_GRAY),
                 font=("Helvetica", 10, "bold")).pack(side="right")
        tk.Frame(inner, bg="#1a1a1a", height=1).pack(
            fill="x", padx=PAD, pady=(14, 0))

        # ── Metadata ──────────────────────────────────────────────────────────
        self._sec(inner, PAD, "CASE METADATA")
        mc = _card(inner, PAD)
        meta_rows = [
            ("Platform",   case.get("platform")       or "Instagram"),
            ("Scheduled",  case.get("scheduled_date") or "—"),
            ("Filename",   case.get("filename")        or "—"),
            ("Buffer ID",  case.get("buffer_post_id") or "—"),
            ("Created",    (case.get("created_at")    or "")[:19].replace("T", "  ")),
        ]
        for i, (lbl, val) in enumerate(meta_rows):
            rb = "#0d0d0d" if i % 2 == 0 else "#111111"
            row = tk.Frame(mc, bg=rb)
            row.pack(fill="x")
            tk.Label(row, text=lbl, bg=rb, fg=LIGHT_GRAY,
                     font=("Helvetica", 8, "bold"), width=12,
                     anchor="w").pack(side="left", padx=(12, 0), pady=7)
            tk.Label(row, text=str(val)[:90], bg=rb, fg=WHITE,
                     font=("Helvetica", 9), anchor="w").pack(
                     side="left", fill="x", expand=True, padx=8, pady=7)

        # ── Archive URL ───────────────────────────────────────────────────────
        arch = (case.get("archive_url") or "").strip()
        if arch:
            self._sec(inner, PAD, "ARCHIVE URL")
            af = _card(inner, PAD)
            _url_row(af, arch)
            br = tk.Frame(af, bg="#0d0d0d")
            br.pack(side="right", padx=8, pady=6)
            self._mini(br, "Copy", lambda u=arch: self._copy(u))
            self._mini(br, "Open", lambda u=arch: subprocess.Popen(["open", u]))

        # ── Source URL ────────────────────────────────────────────────────────
        src = (case.get("source_url") or "").strip()
        if src:
            self._sec(inner, PAD, "SOURCE URL")
            sf = _card(inner, PAD)
            _url_row(sf, src)
            self._mini(sf, "Open", lambda u=src: subprocess.Popen(["open", u]),
                       side="right")

        # ── Caption editor ────────────────────────────────────────────────────
        self._sec(inner, PAD, "BUFFER CAPTION")
        cw = tk.Frame(inner, bg="#1a1a1a",
                      highlightthickness=1, highlightbackground="#2a2a2a")
        cw.pack(fill="x", padx=PAD)
        self._cap = tk.Text(cw, bg="#1a1a1a", fg=WHITE,
                            insertbackground=WHITE, font=("Helvetica", 10),
                            bd=0, relief="flat", highlightthickness=0,
                            wrap="word", height=11)
        self._cap.pack(fill="x", padx=8, pady=8)
        self._cap.insert("1.0", case.get("caption") or "")
        cf = tk.Frame(inner, bg=BG)
        cf.pack(fill="x", padx=PAD, pady=(4, 0))
        self._char_lbl = tk.Label(cf, text="", bg=BG, fg=MUTED,
                                   font=("Helvetica", 8))
        self._char_lbl.pack(side="left")
        self._cap.bind("<KeyRelease>", self._upd_chars)
        self._upd_chars()
        self._mini(cf, "SAVE CAPTION", self._save_caption,
                   side="right", bg=CRIMSON, fg=WHITE, hbg=CRIMSON_HOT)

        # ── Status update ─────────────────────────────────────────────────────
        self._sec(inner, PAD, "UPDATE STATUS")
        sr = tk.Frame(inner, bg=BG)
        sr.pack(fill="x", padx=PAD, pady=(0, 0))
        self._status_var = tk.StringVar(value=case.get("status") or "Draft")
        ttk.Combobox(sr, textvariable=self._status_var,
                     values=ALL_STATUSES, state="readonly",
                     font=("Helvetica", 11), width=18).pack(side="left")
        self._mini(sr, "UPDATE", self._save_status,
                   side="left", bg="#1a1a1a", fg=WHITE, hbg="#2a2a2a", px=8)

        # ── Thumbnail ─────────────────────────────────────────────────────────
        self._sec(inner, PAD, "THUMBNAIL")
        tc = _card(inner, PAD)
        ti = tk.Frame(tc, bg="#0d0d0d")
        ti.pack(fill="x", padx=12, pady=12)
        self._thumb_lbl = tk.Label(ti, bg="#111111", fg="#333333",
                                    text="No thumbnail",
                                    font=("Helvetica", 9),
                                    width=24, height=8)
        self._thumb_lbl.pack(side="left")
        tp = (case.get("thumbnail_path") or "").strip()
        thumb_path = self.library._resolve_path(tp) if tp else Path("")
        if tp and thumb_path.exists():
            self._load_thumb(str(thumb_path))
        tb = tk.Frame(ti, bg="#0d0d0d")
        tb.pack(side="left", fill="y", padx=(14, 0))
        self._mini(tb, "Regenerate",
                   lambda: self._regen_thumb(),
                   bg="#1a1a1a", fg=WHITE, hbg="#2a2a2a",
                   fill=True, py=5)
        self._mini(tb, "Choose Image",
                   self._pick_thumb,
                   bg="#1a1a1a", fg=WHITE, hbg="#2a2a2a",
                   fill=True, py=5)

        # ── Processing timeline ───────────────────────────────────────────────
        self._sec(inner, PAD, "PROCESSING TIMELINE")
        tlc = _card(inner, PAD)
        timeline = case.get("timeline") or []
        if timeline:
            for evt in timeline[:12]:
                ts  = (evt.get("event_time") or "")[:19].replace("T", "  ")
                lbl = evt.get("event_label") or ""
                det = evt.get("detail") or ""
                er  = tk.Frame(tlc, bg="#0d0d0d")
                er.pack(fill="x", padx=12, pady=2)
                tk.Label(er, text=ts, bg="#0d0d0d", fg="#3a3a3a",
                         font=("Courier", 8), width=20, anchor="w").pack(side="left")
                text = f"{lbl}  {det}".strip()
                tk.Label(er, text=text, bg="#0d0d0d", fg=LIGHT_GRAY,
                         font=("Helvetica", 8), anchor="w",
                         wraplength=460, justify="left").pack(
                         side="left", fill="x", expand=True)
        else:
            tk.Label(tlc, text="No events recorded.",
                     bg="#0d0d0d", fg="#2a2a2a",
                     font=("Helvetica", 9)).pack(padx=12, pady=8, anchor="w")
        tk.Frame(tlc, bg="#0d0d0d", height=4).pack()

        # ── Delete ────────────────────────────────────────────────────────────
        tk.Frame(inner, bg="#1a1a1a", height=1).pack(
            fill="x", padx=PAD, pady=(22, 0))
        dl = tk.Label(inner, text="▸  DELETE CASE",
                      bg=BG, fg="#2a2a2a",
                      font=("Helvetica", 10, "bold"),
                      cursor="hand2", pady=11, padx=PAD, anchor="w")
        dl.pack(fill="x", pady=(6, 24))
        dl.bind("<Enter>",    lambda e: dl.config(fg=ERROR_RED))
        dl.bind("<Leave>",    lambda e: dl.config(fg="#2a2a2a"))
        dl.bind("<Button-1>", lambda e: self._delete())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sec(self, parent, pad, text):
        tk.Label(parent, text=text, bg=BG, fg=CRIMSON,
                 font=("Helvetica", 8, "bold")).pack(
                 anchor="w", padx=pad, pady=(16, 4))

    def _mini(self, parent, text, cmd, side="left", bg="#1a1a1a",
              fg=WHITE, hbg="#2a2a2a", px=0, py=0, fill=False):
        b = tk.Label(parent, text=text, bg=bg, fg=fg, cursor="hand2",
                     font=("Helvetica", 9, "bold"),
                     padx=10 + px, pady=5 + py)
        b.pack(side=side, padx=(6, 0),
               fill="x" if fill else "none", pady=(4, 0) if fill else 0)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>",    lambda e: b.config(bg=hbg))
        b.bind("<Leave>",    lambda e: b.config(bg=bg))
        return b

    def _upd_chars(self, *_):
        n = len(self._cap.get("1.0", "end").strip())
        self._char_lbl.config(text=f"{n:,} characters", fg=MUTED)

    def _save_caption(self):
        cap = self._cap.get("1.0", "end").strip()
        self.library.update_caption(self.case["id"], cap)
        self._char_lbl.config(text="✓  Saved", fg="#2d8a4e")
        self.after(2200, self._upd_chars)
        self.after(2200, lambda: self._char_lbl.config(fg=MUTED))

    def _save_status(self):
        self.library.update_status(self.case["id"], self._status_var.get())

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _load_thumb(self, path: str):
        try:
            from PIL import Image, ImageTk
            img   = Image.open(self.library._resolve_path(path))
            img.thumbnail((300, 534), Image.LANCZOS)   # preserve 9:16
            photo = ImageTk.PhotoImage(img)
            self._thumb_ref = photo
            self._thumb_lbl.config(image=photo, text="", width=0, height=0)
        except Exception:
            pass

    def _regen_thumb(self):
        self.library.regenerate_thumbnail(
            self.case["id"], self.case["case_name"]
        )
        self._thumb_lbl.config(text="Regenerating…", image="",
                               fg=LIGHT_GRAY, width=24, height=8)
        # Refresh image after a delay
        self.after(5000, self._reload_thumb)

    def _reload_thumb(self):
        fresh = self.library.get_by_id(self.case["id"])
        if fresh:
            tp = (fresh.get("thumbnail_path") or "").strip()
            thumb_path = self.library._resolve_path(tp) if tp else Path("")
            if tp and thumb_path.exists():
                self._load_thumb(str(thumb_path))

    def _pick_thumb(self):
        path = filedialog.askopenfilename(
            title="Select thumbnail image",
            filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All", "*.*")]
        )
        if not path:
            return
        try:
            from PIL import Image
            dest = self.library.thumb_dir / f"custom_{self.case['id']}{Path(path).suffix}"
            img  = Image.open(path).convert("RGB")
            img  = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            img.save(str(dest), "JPEG", quality=87)
            self.library.update_thumbnail(self.case["id"], str(dest))
            self._load_thumb(str(dest))
        except Exception as e:
            messagebox.showerror("Thumbnail Error", str(e))

    def _delete(self):
        if messagebox.askyesno(
            "Delete Case",
            "Remove this case from the library?\n(Video file on disk is not deleted.)",
            icon="warning"
        ):
            self.library.delete_case(self.case["id"])
            self._close()


# ─────────────────────────────────────────────────────────────────────────────
# Reusable widget helpers
# ─────────────────────────────────────────────────────────────────────────────

def _card(parent, pad) -> tk.Frame:
    f = tk.Frame(parent, bg="#0d0d0d",
                 highlightthickness=1, highlightbackground="#1a1a1a")
    f.pack(fill="x", padx=pad)
    return f


def _url_row(parent: tk.Frame, url: str):
    display = url if len(url) <= 74 else url[:71] + "…"
    tk.Label(parent, text=display, bg="#0d0d0d", fg="#4a9adf",
             font=("Courier", 9), wraplength=520,
             justify="left", anchor="w").pack(
             side="left", fill="x", expand=True, padx=10, pady=8)


def _hover_label(widget: tk.Label, nbg, hbg, nfg=None, hfg=None):
    widget.bind("<Enter>", lambda e: widget.config(
        bg=hbg, **({"fg": hfg} if hfg else {})))
    widget.bind("<Leave>", lambda e: widget.config(
        bg=nbg, **({"fg": nfg} if nfg else {})))
