"""
Analyses when the creator's top-performing posts went live.
Returns ranked posting windows by day + hour.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytz
from analysis.engagement import get_top_posts

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_best_times(handle: str, creator_timezone: str = "Asia/Kolkata") -> list[dict]:
    """
    Returns posting windows ranked by average relative performance.
    Each entry: {day, hour, label, avg_perf, post_count}
    """
    df = get_top_posts(handle, top_pct=0.25, days=90)
    if df.empty:
        return []

    tz = pytz.timezone(creator_timezone)
    df["local_dt"] = df["post_date"].dt.tz_localize("UTC").dt.tz_convert(tz)
    df["day_of_week"] = df["local_dt"].dt.dayofweek
    df["hour"] = df["local_dt"].dt.hour

    grouped = (
        df.groupby(["day_of_week", "hour"])["relative_perf"]
        .agg(["mean", "count"])
        .reset_index()
    )
    grouped = grouped[grouped["count"] >= 2]
    grouped = grouped.sort_values("mean", ascending=False)

    results = []
    for _, row in grouped.head(5).iterrows():
        day = DAY_NAMES[int(row["day_of_week"])]
        hour = int(row["hour"])
        am_pm = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        display_hour = 12 if display_hour == 0 else display_hour
        results.append({
            "day": day,
            "hour": hour,
            "label": f"{day} {display_hour}{am_pm}",
            "avg_perf": round(float(row["mean"]), 2),
            "post_count": int(row["count"]),
        })

    return results


if __name__ == "__main__":
    import sys
    handle = sys.argv[1] if len(sys.argv) > 1 else "openai"
    times = get_best_times(handle)
    for t in times:
        print(f"{t['label']}: {t['avg_perf']}x avg ({t['post_count']} posts)")
