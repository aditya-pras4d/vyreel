import sqlite3
import os
import re
from datetime import datetime, timezone as dt_timezone

# Override with VYREEL_DB_PATH to point at a persistent disk in production
# (otherwise the SQLite file lives next to the code and is wiped on redeploy).
DB_PATH = os.environ.get("VYREEL_DB_PATH") or os.path.join(os.path.dirname(__file__), "vyreel.db")

# Instagram allows letters, digits, dots and underscores, max 30 chars.
# Also blocks path traversal — the handle ends up in PDF filenames.
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
# Leading '+' is mandatory — it's the only reliable signal that the country
# code is included, which WhatsApp delivery requires.
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
# Deliberately permissive: one '@', a dot in the domain, no spaces. Mirrors the
# EMAIL_RE used in the onboarding form so both layers agree on what's valid.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_handle(handle: str) -> bool:
    return bool(HANDLE_RE.match((handle or "").lstrip("@")))


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def normalize_phone(phone: str) -> str | None:
    """Returns E.164 digits without the '+' (e.g. '919876543210'), or None if invalid.
    Requires a leading '+' and country code — WhatsApp needs the full international number."""
    cleaned = re.sub(r"[\s\-().]", "", phone or "")
    if PHONE_RE.match(cleaned):
        return cleaned.lstrip("+")
    return None


def utc_iso(dt: datetime) -> str:
    """Canonical stored datetime format: naive UTC, second precision.
    All collectors must store datetimes through this so string comparisons work."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(dt_timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS creators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            niche TEXT NOT NULL DEFAULT 'ai-tech',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            backfilled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS competitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL REFERENCES creators(id),
            handle TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',  -- confirmed | suggested
            UNIQUE(creator_id, handle)
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle TEXT NOT NULL,
            shortcode TEXT UNIQUE NOT NULL,
            post_date TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            video_views INTEGER DEFAULT 0,
            post_type TEXT,  -- GraphVideo | GraphImage | GraphSidecar
            caption TEXT,
            is_competitor INTEGER NOT NULL DEFAULT 0,
            collected_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS reddit_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subreddit TEXT NOT NULL,
            title TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            num_comments INTEGER DEFAULT 0,
            created_utc TEXT NOT NULL,
            post_id TEXT UNIQUE NOT NULL,
            collected_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS youtube_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            channel TEXT,
            view_count INTEGER DEFAULT 0,
            published_at TEXT NOT NULL,
            collected_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS trend_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            interest_score INTEGER DEFAULT 0,
            date TEXT NOT NULL,
            collected_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(keyword, date)
        );

        CREATE TABLE IF NOT EXISTS news_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headline TEXT NOT NULL,
            source TEXT,
            published_at TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            collected_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL REFERENCES creators(id),
            generated_at TEXT NOT NULL DEFAULT (datetime('now')),
            confidence_score REAL NOT NULL,
            top_topic TEXT,
            pdf_path TEXT,
            sent_at TEXT
        );

        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            handle TEXT,            -- Instagram handle, stored without '@'
            name TEXT,
            niche TEXT,             -- creator niche, e.g. 'ai-tech'
            about TEXT,             -- optional free-text "about yourself"
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)

    conn.commit()
    conn.close()


def add_creator(handle, email, phone, timezone, competitors=None):
    handle = handle.lstrip("@")
    if not valid_handle(handle):
        raise ValueError(f"Invalid Instagram handle: {handle!r}")
    phone_norm = normalize_phone(phone)
    if not phone_norm:
        raise ValueError(f"Invalid phone number (country code required): {phone!r}")

    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO creators (handle, email, phone, timezone) VALUES (?, ?, ?, ?)",
            (handle, email or "", phone_norm, timezone),
        )
        creator_id = c.lastrowid
        if competitors:
            for comp in competitors:
                comp = comp.strip().lstrip("@")
                if comp and valid_handle(comp):
                    c.execute(
                        "INSERT OR IGNORE INTO competitors (creator_id, handle, status) VALUES (?, ?, 'confirmed')",
                        (creator_id, comp),
                    )
        conn.commit()
        return creator_id
    finally:
        conn.close()


def get_creator(handle):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM creators WHERE handle = ?", (handle.lstrip("@"),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_creators():
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM creators").fetchall()]
    finally:
        conn.close()


def get_competitors(creator_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT handle FROM competitors WHERE creator_id = ? AND status = 'confirmed'",
            (creator_id,),
        ).fetchall()
        return [r["handle"] for r in rows]
    finally:
        conn.close()


class AlreadyOnWaitlistError(Exception):
    """Raised when an email is submitted to the waitlist a second time."""


def add_to_waitlist(email, handle=None, name=None, niche=None, about=None):
    """Insert a waitlist signup. Returns (id, position) where position is the
    1-based join order. Raises ValueError for a bad email and
    AlreadyOnWaitlistError if the email is already registered."""
    email = (email or "").strip().lower()
    if not valid_email(email):
        raise ValueError(f"Invalid email address: {email!r}")

    handle = (handle or "").strip().lstrip("@") or None
    if handle and not valid_handle(handle):
        raise ValueError(f"Invalid Instagram handle: {handle!r}")

    name = (name or "").strip() or None
    niche = (niche or "").strip() or None
    about = (about or "").strip() or None

    conn = get_conn()
    try:
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO waitlist (email, handle, name, niche, about) VALUES (?, ?, ?, ?, ?)",
                (email, handle, name, niche, about),
            )
        except sqlite3.IntegrityError:
            raise AlreadyOnWaitlistError(email)
        new_id = c.lastrowid
        conn.commit()
        # Position = number of rows at or before this one (stable by id).
        position = conn.execute(
            "SELECT COUNT(*) FROM waitlist WHERE id <= ?", (new_id,)
        ).fetchone()[0]
        return new_id, position
    finally:
        conn.close()


def get_waitlist_count():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    finally:
        conn.close()


def get_waitlist(limit=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM waitlist ORDER BY id"
        params = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DB_PATH}")
