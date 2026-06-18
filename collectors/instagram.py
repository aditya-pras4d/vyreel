"""
Pulls public post data from Instagram using Instaloader.
- backfill: 50 posts per handle (one-time history pull)
- collect_recent: 10 latest posts per competitor (regular cycle)
- collect_hashtags: top posts from AI/tech hashtags (trend signal)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import os
import time
import instaloader
from db import get_conn, get_all_creators, get_competitors, utc_iso

L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    quiet=True,
)

HASHTAGS = [
    "aitools",
    "artificialintelligence",
    "chatgpt",
    "llm",
    "generativeai",
    "machinelearning",
    "claudeai",
    "openai",
    "vibecoding",
    "aiagents",
]

HASHTAG_POSTS_LIMIT = 15


def _insert_posts(conn, handle: str, posts_iter, max_posts: int, is_competitor: bool) -> int:
    inserted = 0
    for i, post in enumerate(posts_iter):
        if i >= max_posts:
            break
        # Upsert: re-scraping a known post refreshes its metrics, so likes/views
        # aren't frozen at whatever they were the first time we saw the post.
        is_new = conn.execute(
            "SELECT 1 FROM posts WHERE shortcode = ?", (post.shortcode,)
        ).fetchone() is None
        conn.execute(
            """INSERT INTO posts
               (handle, shortcode, post_date, likes, video_views, post_type, caption, is_competitor)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(shortcode) DO UPDATE SET
                 likes = excluded.likes,
                 video_views = excluded.video_views,
                 caption = excluded.caption,
                 collected_at = datetime('now')""",
            (
                handle,
                post.shortcode,
                utc_iso(post.date_utc),
                post.likes,
                post.video_view_count if post.is_video else 0,
                post.typename,
                (post.caption or "")[:1000],
                1 if is_competitor else 0,
            ),
        )
        if is_new:
            inserted += 1
        time.sleep(0.5)
    return inserted


def collect(handle: str, max_posts: int = 50, is_competitor: bool = False) -> int:
    """Full backfill for a single handle."""
    handle = handle.lstrip("@")
    print(f"[instagram] backfill @{handle} (max {max_posts})")
    try:
        profile = instaloader.Profile.from_username(L.context, handle)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"[instagram] @{handle} not found, skipping")
        return 0

    conn = get_conn()
    try:
        inserted = _insert_posts(conn, handle, profile.get_posts(), max_posts, is_competitor)
        conn.commit()
    finally:
        conn.close()

    print(f"[instagram] @{handle}: {inserted} new posts stored")
    return inserted


def collect_recent_competitors() -> int:
    """Pulls last 10 posts from every competitor across all creators. Runs in regular collect cycle."""
    creators = get_all_creators()
    seen = set()
    total = 0

    for creator in creators:
        competitors = get_competitors(creator["id"])
        for comp in competitors:
            comp = comp.lstrip("@")
            if comp in seen:
                continue
            seen.add(comp)

            print(f"[instagram] recent @{comp}")
            try:
                profile = instaloader.Profile.from_username(L.context, comp)
                conn = get_conn()
                try:
                    inserted = _insert_posts(conn, comp, profile.get_posts(), 10, is_competitor=True)
                    conn.commit()
                    total += inserted
                finally:
                    conn.close()
                time.sleep(3)
            except Exception as e:
                print(f"[instagram] @{comp} failed: {e}")
                time.sleep(2)

    print(f"[instagram] competitors: {total} new posts stored")
    return total


def collect_hashtags() -> int:
    """Pulls top posts from AI/tech hashtags as trend signals. Requires Instagram login — skipped if not configured."""
    ig_user = os.environ.get("INSTAGRAM_USER")
    ig_pass = os.environ.get("INSTAGRAM_PASS")
    if not ig_user or not ig_pass:
        print("[instagram] INSTAGRAM_USER/PASS not set, skipping hashtag collection")
        return 0

    try:
        L.login(ig_user, ig_pass)
    except Exception as e:
        print(f"[instagram] login failed: {e}, skipping hashtag collection")
        return 0

    total = 0
    for tag in HASHTAGS:
        print(f"[instagram] hashtag #{tag}")
        try:
            hashtag = instaloader.Hashtag.from_name(L.context, tag)
            conn = get_conn()
            try:
                inserted = _insert_posts(
                    conn, f"#{tag}", hashtag.get_top_posts(), HASHTAG_POSTS_LIMIT, is_competitor=True
                )
                conn.commit()
                total += inserted
            finally:
                conn.close()
            time.sleep(4)
        except Exception as e:
            print(f"[instagram] #{tag} failed: {e}")
            time.sleep(2)

    print(f"[instagram] hashtags: {total} new posts stored")
    return total


def collect_for_creator(creator_id: int, handle: str, competitors: list[str]):
    """Used by backfill command."""
    collect(handle, max_posts=50, is_competitor=False)
    time.sleep(2)
    for comp in competitors:
        collect(comp, max_posts=50, is_competitor=True)
        time.sleep(3)


if __name__ == "__main__":
    handle = sys.argv[1] if len(sys.argv) > 1 else "openai"
    collect(handle)
