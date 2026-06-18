"""
Pulls AI/tech news from RSS feeds using Feedparser.
Stores results in news_signals table. No API key needed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from db import get_conn, utc_iso

RSS_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("MIT Tech Review AI", "https://www.technologyreview.com/feed/"),
    ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("ArsTechnica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
]


def _parse_date(entry) -> datetime | None:
    for field in ("published", "updated"):
        raw = getattr(entry, field, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def collect(hours_back: int = 24):
    print(f"[news] collecting RSS feeds from last {hours_back}h")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    conn = get_conn()
    inserted = 0

    try:
        for source_name, url in RSS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub_date = _parse_date(entry)
                    if not pub_date or pub_date < cutoff:
                        continue

                    link = getattr(entry, "link", "")
                    title = getattr(entry, "title", "").strip()
                    if not link or not title:
                        continue

                    conn.execute(
                        """INSERT OR IGNORE INTO news_signals
                           (headline, source, published_at, link)
                           VALUES (?, ?, ?, ?)""",
                        (title, source_name, utc_iso(pub_date), link),
                    )
                    if conn.execute("SELECT changes()").fetchone()[0]:
                        inserted += 1

            except Exception as e:
                print(f"[news] error parsing {source_name}: {e}")

        conn.commit()
    finally:
        conn.close()

    print(f"[news] {inserted} new headlines stored")
    return inserted


if __name__ == "__main__":
    collect()
