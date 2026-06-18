"""
Post-onboarding background job: suggests competitors for a creator.
Runs after signup, not during. Saves suggestions to DB with status='suggested'.
Update SEED_ACCOUNTS list manually as the niche evolves.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
import instaloader
from db import get_conn

# Hardcoded AI/tech Instagram seed accounts — update this list as needed
SEED_ACCOUNTS = [
    "ai.breakthroughs",
    "artificialintelligencehub",
    "techinsider",
    "futurism",
    "wired",
    "theverge",
    "openai",
    "anthropic_ai",
    "googleai",
    "metaai",
    "huggingface",
    "mistral_ai",
    "stability_ai",
    "midjourney",
    "perplexity_ai",
    "groq_inc",
    "nvidia_ai",
    "tesla_ai",
    "deepmind",
    "aitools.daily",
    "aitoolsguide",
    "futuretools.io",
    "theaigeek",
    "geeky.ai",
    "ai.explained_",
    "ai_daily_digest",
    "theneuralbridge",
    "allagentai",
    "aitoolsbox",
    "aibreakthrough_",
]

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


def _get_follower_count(handle: str) -> int:
    try:
        profile = instaloader.Profile.from_username(L.context, handle)
        return profile.followers
    except Exception:
        return 0


def suggest_for_creator(creator_id: int, top_n: int = 5):
    """
    Scores seed accounts and saves top N as 'suggested' competitors.
    Skips accounts already confirmed for this creator.
    """
    conn = get_conn()
    try:
        existing = {
            r["handle"]
            for r in conn.execute(
                "SELECT handle FROM competitors WHERE creator_id = ?", (creator_id,)
            ).fetchall()
        }
    finally:
        conn.close()

    candidates = [h for h in SEED_ACCOUNTS if h not in existing]

    scored = []
    for handle in candidates:
        followers = _get_follower_count(handle)
        if followers > 1000:
            scored.append((handle, followers))
        time.sleep(1.5)

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_n]

    if not top:
        print(f"[suggester] creator {creator_id}: no suggestions found")
        return

    conn = get_conn()
    try:
        for handle, _ in top:
            conn.execute(
                """INSERT OR IGNORE INTO competitors (creator_id, handle, status)
                   VALUES (?, ?, 'suggested')""",
                (creator_id, handle),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"[suggester] creator {creator_id}: {len(top)} suggestions saved")


if __name__ == "__main__":
    creator_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    suggest_for_creator(creator_id)
