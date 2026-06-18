"""
Generates a sample brief PDF with realistic dummy data.
Run: python sample_brief.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from brief.pdf import render_pdf

SAMPLE_BRIEF_TEXT = """## What's Working Right Now

- **AI Agents** content is outperforming every other topic this week — competitor accounts covering agentic workflows are averaging **4.1x** their normal views. The audience is actively hungry for this.
- **Reels under 60 seconds** are the dominant format right now, accounting for 78% of top-performing posts across your competitor set in the last 7 days.
- Google Trends shows "AI agent" hitting an interest score of **84/100** — the highest it's been in 3 months. Reddit's r/artificial has 6 posts on the topic in the top 20 hot posts today.

## What to Avoid Today

- **"Top 10 AI tools" listicles** — 4 of your 5 tracked competitors posted this format in the last 48 hours. The window is saturated, engagement is flat.
- **ChatGPT vs Gemini comparisons** — oversaturated at the niche level, trending down on Google Trends for the second consecutive week.

## Today's Recommendation

**Topic:** How AI agents are replacing entire workflows — not just tasks
**Angle:** Most creators are covering what AI agents *are*. Nobody in your competitor set has covered what they *replace* at the workflow level. That's your gap.
**Format:** Reel, 45–55 seconds
**Posting time:** Tuesday 7PM IST
**Opening caption line:** "You don't need a team for this anymore — one AI agent just replaced my entire research workflow."

## Why This Will Work

AI Agents surfaced across **4 out of 5** signal sources today — Reddit, YouTube, Google Trends, and breaking news from TechCrunch — with a combined signal score of 91. None of your 5 tracked competitors have posted on this specific angle in the last 7 days, leaving the window completely open. Your Reels are currently performing at **3.8x** your account baseline, and Tuesday 7PM is your single highest-performing slot based on your last 90 days of data.
"""

SAMPLE_RESULT = {
    "handle": "stics.ai",
    "topic": "AI Agents",
    "confidence_score": 0.87,
    "source_count": 4,
    "sources": ["reddit", "youtube", "trends", "news"],
    "gap_score": 1.0,
    "covered_by": [],
    "competitor_posts": [],
    "example_signals": [
        ("reddit", "AI agents are about to replace entire departments, not just tasks"),
        ("youtube", "I Built an AI Agent That Runs My Entire Business"),
        ("trends", "ai agent — interest score 84/100"),
        ("news", "TechCrunch: Agentic AI is the next frontier for enterprise automation"),
    ],
    "winning_format": {
        "format": "Reels",
        "raw_type": "GraphVideo",
        "multiplier": 3.8,
        "all_formats": {"Reels": 3.8, "Carousels": 1.4, "Images": 0.9},
    },
    "best_times": [
        {"day": "Tuesday", "hour": 19, "label": "Tuesday 7PM", "avg_perf": 4.2, "post_count": 8},
        {"day": "Wednesday", "hour": 18, "label": "Wednesday 6PM", "avg_perf": 3.6, "post_count": 6},
    ],
}

if __name__ == "__main__":
    path = render_pdf("stics.ai", SAMPLE_BRIEF_TEXT, SAMPLE_RESULT)
    print(f"\nSample brief generated → {path}")
