"""
Pulls new posts from AI/tech subreddits via Reddit's public JSON endpoints
(no API key needed — just a descriptive User-Agent).

Unlike the old RSS approach, the JSON endpoint includes real score and comment
counts, and re-collecting refreshes them — so trend velocity actually works.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
import requests
from datetime import datetime, timezone, timedelta
from db import get_conn, utc_iso

HEADERS = {"User-Agent": "vyreel-collector/1.0 (content trend research)"}

SUBREDDITS = [
    "ChatGPT",           # 11.5M — largest AI community
    "singularity",       # 3.9M — AGI/LLM opinions, early signal
    "MachineLearning",   # 3.1M — research papers break here
    "ArtificialInteligence",  # 1.7M — broad AI news (note: intentional typo in subreddit name)
    "OpenAI",            # 590k — OpenAI-specific news and reactions
    "artificial",        # 500k — broad AI news
    "LocalLLaMA",        # 742k — open-source model discourse
    "PromptEngineering", # 301k — relevant for content creators
    "generativeAI",      # 300k — generative AI tools
    "LLMDevs",           # 125k — high signal developer community
    "ClaudeAI",          # Claude/Anthropic community
    "Anthropic",         # Anthropic news and announcements
    "GeminiAI",          # Google AI, good for comparative content
    "perplexity_ai",     # AI search, fast growing
]


def collect(hours_back: int = 24):
    print(f"[reddit] collecting via JSON API from last {hours_back}h")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    conn = get_conn()
    inserted = 0

    try:
        for sub in SUBREDDITS:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=50"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                children = resp.json().get("data", {}).get("children", [])
            except Exception as e:
                print(f"[reddit] r/{sub} failed: {e}")
                time.sleep(2)
                continue

            for child in children:
                p = child.get("data", {})
                title = (p.get("title") or "").strip()
                post_id = p.get("id")
                created_ts = p.get("created_utc")
                if not title or not post_id or not created_ts:
                    continue

                created = datetime.fromtimestamp(created_ts, tz=timezone.utc)
                if created < cutoff:
                    continue

                # Upsert so score/comments keep updating as the post gains traction
                is_new = conn.execute(
                    "SELECT 1 FROM reddit_signals WHERE post_id = ?", (post_id,)
                ).fetchone() is None
                conn.execute(
                    """INSERT INTO reddit_signals
                       (subreddit, title, score, num_comments, created_utc, post_id)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(post_id) DO UPDATE SET
                         score = excluded.score,
                         num_comments = excluded.num_comments,
                         collected_at = datetime('now')""",
                    (sub, title, int(p.get("score") or 0), int(p.get("num_comments") or 0),
                     utc_iso(created), post_id),
                )
                if is_new:
                    inserted += 1

            time.sleep(1)

        conn.commit()
    finally:
        conn.close()

    print(f"[reddit] {inserted} new signals stored")
    return inserted


if __name__ == "__main__":
    collect()
