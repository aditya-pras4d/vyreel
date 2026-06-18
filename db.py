import psycopg2
import psycopg2.extras
import psycopg2.errors
import os
import re
from datetime import datetime, timezone as dt_timezone

# Postgres connection string (Supabase). Set DATABASE_URL in the environment, e.g.
#   postgresql://postgres.<ref>:<password>@<host>.pooler.supabase.com:6543/postgres
DATABASE_URL = os.environ.get("DATABASE_URL")

# Postgres expression that reproduces utc_iso()'s format (naive UTC, second
# precision) so column DEFAULTs match values written by the collectors.
_NOW_ISO = "to_char((now() at time zone 'utc'), 'YYYY-MM-DD\"T\"HH24:MI:SS')"

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
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at your Supabase Postgres "
            "connection string (Project Settings -> Database -> Connection string)."
        )
    # sslmode=require: Supabase mandates TLS. If the URL already specifies an
    # sslmode this keyword takes precedence, which is the behaviour we want.
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    return conn


def init_db():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS creators (
                id SERIAL PRIMARY KEY,
                handle TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
                niche TEXT NOT NULL DEFAULT 'ai-tech',
                created_at TEXT NOT NULL DEFAULT {_NOW_ISO},
                backfilled_at TEXT
            );

            CREATE TABLE IF NOT EXISTS competitors (
                id SERIAL PRIMARY KEY,
                creator_id INTEGER NOT NULL REFERENCES creators(id),
                handle TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',  -- confirmed | suggested
                UNIQUE(creator_id, handle)
            );

            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                handle TEXT NOT NULL,
                shortcode TEXT UNIQUE NOT NULL,
                post_date TEXT NOT NULL,
                likes INTEGER DEFAULT 0,
                video_views INTEGER DEFAULT 0,
                post_type TEXT,  -- GraphVideo | GraphImage | GraphSidecar
                caption TEXT,
                is_competitor INTEGER NOT NULL DEFAULT 0,
                collected_at TEXT NOT NULL DEFAULT {_NOW_ISO}
            );

            CREATE TABLE IF NOT EXISTS reddit_signals (
                id SERIAL PRIMARY KEY,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                num_comments INTEGER DEFAULT 0,
                created_utc TEXT NOT NULL,
                post_id TEXT UNIQUE NOT NULL,
                collected_at TEXT NOT NULL DEFAULT {_NOW_ISO}
            );

            CREATE TABLE IF NOT EXISTS youtube_signals (
                id SERIAL PRIMARY KEY,
                video_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                channel TEXT,
                view_count INTEGER DEFAULT 0,
                published_at TEXT NOT NULL,
                collected_at TEXT NOT NULL DEFAULT {_NOW_ISO}
            );

            CREATE TABLE IF NOT EXISTS trend_signals (
                id SERIAL PRIMARY KEY,
                keyword TEXT NOT NULL,
                interest_score INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                collected_at TEXT NOT NULL DEFAULT {_NOW_ISO},
                UNIQUE(keyword, date)
            );

            CREATE TABLE IF NOT EXISTS news_signals (
                id SERIAL PRIMARY KEY,
                headline TEXT NOT NULL,
                source TEXT,
                published_at TEXT NOT NULL,
                link TEXT UNIQUE NOT NULL,
                collected_at TEXT NOT NULL DEFAULT {_NOW_ISO}
            );

            CREATE TABLE IF NOT EXISTS briefs (
                id SERIAL PRIMARY KEY,
                creator_id INTEGER NOT NULL REFERENCES creators(id),
                generated_at TEXT NOT NULL DEFAULT {_NOW_ISO},
                confidence_score DOUBLE PRECISION NOT NULL,
                top_topic TEXT,
                pdf_path TEXT,
                sent_at TEXT
            );

            CREATE TABLE IF NOT EXISTS waitlist (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                handle TEXT,            -- Instagram handle, stored without '@'
                name TEXT,
                niche TEXT,             -- creator niche, e.g. 'ai-tech'
                about TEXT,             -- optional free-text "about yourself"
                created_at TEXT NOT NULL DEFAULT {_NOW_ISO}
            );
        """)
        conn.commit()
    finally:
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
            "INSERT INTO creators (handle, email, phone, timezone) VALUES (%s, %s, %s, %s) RETURNING id",
            (handle, email or "", phone_norm, timezone),
        )
        creator_id = c.fetchone()["id"]
        if competitors:
            for comp in competitors:
                comp = comp.strip().lstrip("@")
                if comp and valid_handle(comp):
                    c.execute(
                        "INSERT INTO competitors (creator_id, handle, status) VALUES (%s, %s, 'confirmed') "
                        "ON CONFLICT (creator_id, handle) DO NOTHING",
                        (creator_id, comp),
                    )
        conn.commit()
        return creator_id
    finally:
        conn.close()


def get_creator(handle):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM creators WHERE handle = %s", (handle.lstrip("@"),))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_creators():
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM creators")
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


def get_competitors(creator_id):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT handle FROM competitors WHERE creator_id = %s AND status = 'confirmed'",
            (creator_id,),
        )
        return [r["handle"] for r in c.fetchall()]
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
                "INSERT INTO waitlist (email, handle, name, niche, about) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (email, handle, name, niche, about),
            )
            new_id = c.fetchone()["id"]
        except psycopg2.IntegrityError:
            conn.rollback()
            raise AlreadyOnWaitlistError(email)
        # Position = number of rows at or before this one (stable by id).
        c.execute("SELECT COUNT(*) AS n FROM waitlist WHERE id <= %s", (new_id,))
        position = c.fetchone()["n"]
        conn.commit()
        return new_id, position
    finally:
        conn.close()


def get_waitlist_count():
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) AS n FROM waitlist")
        return c.fetchone()["n"]
    finally:
        conn.close()


def get_waitlist(limit=None):
    conn = get_conn()
    try:
        c = conn.cursor()
        sql = "SELECT * FROM waitlist ORDER BY id"
        params = ()
        if limit is not None:
            sql += " LIMIT %s"
            params = (limit,)
        c.execute(sql, params)
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DATABASE_URL}")
