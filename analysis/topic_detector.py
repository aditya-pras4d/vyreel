"""
Extracts keywords from all signal tables and groups them by topic.
Returns topics ranked by cross-source confidence.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from db import get_conn, utc_iso
from analysis.keywords import extract_topics as _extract_topics


def detect(hours_back: int = 24) -> list[dict]:
    """
    Returns a list of topics sorted by cross-source signal strength.
    Each entry: {topic, sources, source_count, total_signal, signals}
    """
    cutoff = utc_iso(datetime.now(timezone.utc) - timedelta(hours=hours_back))
    conn = get_conn()

    topic_sources: dict[str, dict] = defaultdict(lambda: {
        "sources": set(),
        "total_signal": 0,
        "signals": [],
    })

    try:
        # Reddit
        rows = conn.execute(
            "SELECT title, score FROM reddit_signals WHERE created_utc > ?", (cutoff,)
        ).fetchall()
        for row in rows:
            for topic in _extract_topics(row["title"]):
                topic_sources[topic]["sources"].add("reddit")
                topic_sources[topic]["total_signal"] += row["score"]
                topic_sources[topic]["signals"].append(("reddit", row["title"][:80]))

        # YouTube
        rows = conn.execute(
            "SELECT title, view_count FROM youtube_signals WHERE published_at > ?", (cutoff,)
        ).fetchall()
        for row in rows:
            for topic in _extract_topics(row["title"]):
                topic_sources[topic]["sources"].add("youtube")
                topic_sources[topic]["total_signal"] += row["view_count"] // 1000
                topic_sources[topic]["signals"].append(("youtube", row["title"][:80]))

        # Trends
        rows = conn.execute(
            "SELECT keyword, interest_score FROM trend_signals WHERE date >= date('now', '-1 day')"
        ).fetchall()
        for row in rows:
            for topic in _extract_topics(row["keyword"]):
                if row["interest_score"] >= 60:
                    topic_sources[topic]["sources"].add("trends")
                    topic_sources[topic]["total_signal"] += row["interest_score"]
                    topic_sources[topic]["signals"].append(("trends", row["keyword"]))

        # News
        rows = conn.execute(
            "SELECT headline FROM news_signals WHERE published_at > ?", (cutoff,)
        ).fetchall()
        for row in rows:
            for topic in _extract_topics(row["headline"]):
                topic_sources[topic]["sources"].add("news")
                topic_sources[topic]["total_signal"] += 10
                topic_sources[topic]["signals"].append(("news", row["headline"][:80]))

        # Instagram competitor posts
        rows = conn.execute(
            "SELECT caption FROM posts WHERE is_competitor = 1 AND post_date > ?", (cutoff,)
        ).fetchall()
        for row in rows:
            for topic in _extract_topics(row["caption"] or ""):
                topic_sources[topic]["sources"].add("instagram")
                topic_sources[topic]["total_signal"] += 5
                topic_sources[topic]["signals"].append(("instagram", (row["caption"] or "")[:80]))

    finally:
        conn.close()

    results = []
    for topic, data in topic_sources.items():
        results.append({
            "topic": topic,
            "sources": list(data["sources"]),
            "source_count": len(data["sources"]),
            "total_signal": data["total_signal"],
            "signals": data["signals"][:5],
        })

    results.sort(key=lambda x: (x["source_count"], x["total_signal"]), reverse=True)
    return results


if __name__ == "__main__":
    topics = detect()
    for t in topics[:10]:
        print(f"{t['topic']}: {t['source_count']} sources, signal={t['total_signal']} — {t['sources']}")
