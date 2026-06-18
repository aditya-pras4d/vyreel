"""
Pulls Google Trends interest scores for AI/tech keywords using Pytrends.
Stores results in trend_signals table.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
from datetime import date
from pytrends.request import TrendReq
from db import get_conn

KEYWORDS = [
    "ChatGPT",
    "artificial intelligence",
    "AI tools",
    "Claude AI",
    "Gemini AI",
    "AI agent",
    "LLM",
    "AI automation",
    "Sora AI",
    "AI video generator",
]

TRENDING_THRESHOLD = 60


def collect():
    print("[trends] collecting Google Trends data")
    pytrends = TrendReq(hl="en-US", tz=0)
    today = date.today().isoformat()
    conn = get_conn()
    inserted = 0

    try:
        # Process in batches of 5 (Pytrends limit per request)
        for i in range(0, len(KEYWORDS), 5):
            batch = KEYWORDS[i:i+5]
            try:
                pytrends.build_payload(batch, timeframe="now 7-d")
                interest = pytrends.interest_over_time()
                if interest.empty:
                    continue

                latest = interest.iloc[-1]
                for kw in batch:
                    if kw not in latest:
                        continue
                    score = int(latest[kw])
                    conn.execute(
                        """INSERT OR REPLACE INTO trend_signals (keyword, interest_score, date)
                           VALUES (?, ?, ?)""",
                        (kw, score, today),
                    )
                    inserted += 1

                time.sleep(2)
            except Exception as e:
                print(f"[trends] error for batch {batch}: {e}")
                time.sleep(5)

        conn.commit()
    finally:
        conn.close()

    print(f"[trends] {inserted} keyword scores stored")
    return inserted


if __name__ == "__main__":
    collect()
