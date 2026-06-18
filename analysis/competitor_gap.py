"""
For each trending topic, checks whether the creator's competitors have already covered it.
Returns a gap score: 1.0 = no competitor has covered it, 0.1 = saturated.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db import get_conn
from analysis.keywords import topic_in_text as _topic_in_text


def analyse(topic: str, competitor_handles: list[str], days_back: int = 7) -> dict:
    """
    Returns:
      gap_score: float 0.0-1.0
      covered_by: list of competitor handles that covered the topic
      competitor_posts: example posts
    """
    if not competitor_handles:
        return {"gap_score": 0.7, "covered_by": [], "competitor_posts": []}

    conn = get_conn()
    try:
        placeholders = ",".join("?" * len(competitor_handles))
        rows = conn.execute(
            f"""SELECT handle, caption, post_date, likes, video_views, post_type
                FROM posts
                WHERE handle IN ({placeholders})
                  AND is_competitor = 1
                  AND post_date >= date('now', ?)
                  AND caption IS NOT NULL
                ORDER BY post_date DESC""",
            (*[h.lstrip("@") for h in competitor_handles], f"-{days_back} days"),
        ).fetchall()
    finally:
        conn.close()

    covered_by = set()
    competitor_posts = []

    for row in rows:
        if _topic_in_text(topic, row["caption"]):
            covered_by.add(row["handle"])
            if len(competitor_posts) < 3:
                competitor_posts.append({
                    "handle": row["handle"],
                    "caption_preview": row["caption"][:120],
                    "post_date": row["post_date"],
                })

    count = len(covered_by)
    if count == 0:
        gap_score = 1.0
    elif count <= 2:
        gap_score = 0.5
    else:
        gap_score = 0.1

    return {
        "gap_score": gap_score,
        "covered_by": list(covered_by),
        "competitor_posts": competitor_posts,
    }


if __name__ == "__main__":
    result = analyse("ChatGPT", ["openai", "anthropic_ai"])
    print(result)
