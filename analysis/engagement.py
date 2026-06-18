"""
Benchmarks post performance relative to the account's own baseline.
Returns relative_performance multiplier per post: e.g. 3.2x means 3.2x the account average.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from db import get_conn


def _engagement_metric(row: pd.Series) -> float:
    """Use video_views for reels, likes for images/carousels."""
    if row["post_type"] == "GraphVideo" and row["video_views"] > 0:
        return float(row["video_views"])
    return float(row["likes"])


def get_baseline(handle: str, days: int = 90) -> dict:
    """
    Returns per-format baseline engagement for a given handle.
    {format: avg_engagement, ..., 'overall': avg}
    """
    handle = handle.lstrip("@")
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT post_type, likes, video_views, post_date
               FROM posts
               WHERE handle = ? AND post_date >= date('now', ?)
               ORDER BY post_date DESC""",
            (handle, f"-{days} days"),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {}

    df = pd.DataFrame([dict(r) for r in rows])
    df["engagement"] = df.apply(_engagement_metric, axis=1)

    baseline = {}
    for fmt, group in df.groupby("post_type"):
        baseline[fmt] = group["engagement"].mean()
    baseline["overall"] = df["engagement"].mean()
    return baseline


def get_top_posts(handle: str, top_pct: float = 0.2, days: int = 90) -> pd.DataFrame:
    """Returns top-performing posts (by relative performance) for timing analysis."""
    handle = handle.lstrip("@")
    baseline = get_baseline(handle, days)
    if not baseline:
        return pd.DataFrame()

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT shortcode, post_type, likes, video_views, post_date, caption
               FROM posts
               WHERE handle = ? AND post_date >= date('now', ?)
               ORDER BY post_date DESC""",
            (handle, f"-{days} days"),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["engagement"] = df.apply(_engagement_metric, axis=1)
    df["fmt_baseline"] = df["post_type"].map(lambda t: baseline.get(t, baseline.get("overall", 1)))
    df["relative_perf"] = df["engagement"] / df["fmt_baseline"].clip(lower=1)
    df["post_date"] = pd.to_datetime(df["post_date"])

    threshold = df["relative_perf"].quantile(1 - top_pct)
    return df[df["relative_perf"] >= threshold].copy()


def get_winning_format(handle: str, days: int = 30) -> dict:
    """Returns which post format is outperforming baseline most in the last N days."""
    handle = handle.lstrip("@")
    baseline = get_baseline(handle, 90)
    if not baseline:
        return {}

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT post_type, likes, video_views
               FROM posts
               WHERE handle = ? AND post_date >= date('now', ?)""",
            (handle, f"-{days} days"),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {}

    df = pd.DataFrame([dict(r) for r in rows])
    df["engagement"] = df.apply(_engagement_metric, axis=1)

    results = {}
    for fmt, group in df.groupby("post_type"):
        recent_avg = group["engagement"].mean()
        base = baseline.get(fmt, baseline.get("overall", 1))
        results[fmt] = round(recent_avg / max(base, 1), 2)

    if not results:
        return {}

    best_fmt = max(results, key=results.get)
    fmt_labels = {
        "GraphVideo": "Reels",
        "GraphImage": "Images",
        "GraphSidecar": "Carousels",
    }
    return {
        "format": fmt_labels.get(best_fmt, best_fmt),
        "raw_type": best_fmt,
        "multiplier": results[best_fmt],
        "all_formats": {fmt_labels.get(k, k): v for k, v in results.items()},
    }


if __name__ == "__main__":
    import sys
    handle = sys.argv[1] if len(sys.argv) > 1 else "openai"
    print("Baseline:", get_baseline(handle))
    print("Winning format:", get_winning_format(handle))
