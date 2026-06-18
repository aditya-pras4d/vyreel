"""
Pulls trending AI/tech videos from YouTube Data API v3.
Stores results in youtube_signals table.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from googleapiclient.discovery import build
from db import get_conn, utc_iso

load_dotenv()

SEARCH_QUERIES = [
    "artificial intelligence news",
    "ChatGPT new features",
    "AI tools 2025",
    "large language model",
    "AI automation",
]

MIN_VIEWS = 5000


def collect(hours_back: int = 48):
    print(f"[youtube] collecting videos from last {hours_back}h")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("[youtube] YOUTUBE_API_KEY not set, skipping")
        return 0

    youtube = build("youtube", "v3", developerKey=api_key)
    published_after = (
        datetime.now(timezone.utc) - timedelta(hours=hours_back)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_conn()
    inserted = 0

    try:
        for query in SEARCH_QUERIES:
            response = youtube.search().list(
                q=query,
                part="snippet",
                type="video",
                publishedAfter=published_after,
                maxResults=20,
                relevanceLanguage="en",
                order="viewCount",
            ).execute()

            video_ids = [item["id"]["videoId"] for item in response.get("items", [])]
            if not video_ids:
                continue

            stats_resp = youtube.videos().list(
                part="statistics,snippet",
                id=",".join(video_ids),
            ).execute()

            for item in stats_resp.get("items", []):
                view_count = int(item["statistics"].get("viewCount", 0))
                if view_count < MIN_VIEWS:
                    continue

                # API returns "...Z" format — normalize to the canonical stored format
                published_at = utc_iso(
                    datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
                )
                conn.execute(
                    """INSERT OR IGNORE INTO youtube_signals
                       (video_id, title, channel, view_count, published_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        item["id"],
                        item["snippet"]["title"],
                        item["snippet"]["channelTitle"],
                        view_count,
                        published_at,
                    ),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1

        conn.commit()
    finally:
        conn.close()

    print(f"[youtube] {inserted} new signals stored")
    return inserted


if __name__ == "__main__":
    collect()
