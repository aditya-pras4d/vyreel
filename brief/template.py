"""
Builds the prompt for the LLM from pre-calculated analysis facts.
The LLM writes prose only — no analysis, no invented claims.
"""
from datetime import date


def build_prompt(result: dict) -> str:
    handle = result["handle"]
    topic = result["topic"]
    source_count = result["source_count"]
    sources = ", ".join(result.get("sources", []))
    gap_score = result["gap_score"]
    confidence = int(result["confidence_score"] * 100)
    covered_by = result.get("covered_by", [])
    competitor_posts = result.get("competitor_posts", [])

    winning_fmt = result.get("winning_format", {})
    fmt_name = winning_fmt.get("format", "Reels")
    fmt_multiplier = winning_fmt.get("multiplier", 1.0)

    best_times = result.get("best_times", [])
    best_time_str = best_times[0]["label"] if best_times else "Not enough data yet"
    second_time_str = best_times[1]["label"] if len(best_times) > 1 else ""

    if gap_score >= 1.0:
        gap_desc = f"OPEN — none of the tracked competitors have posted about {topic} in the last 7 days. The window is completely open."
    elif gap_score >= 0.5:
        covered_str = ", ".join(f"@{h}" for h in covered_by[:2])
        gap_desc = f"PARTIAL — {covered_str} have touched this topic but the angle is not saturated. There is still a clear entry point."
    else:
        covered_str = ", ".join(f"@{h}" for h in covered_by[:3])
        gap_desc = f"SATURATED — {covered_str} have already covered this. Recommend a contrarian or niche angle only."

    competitor_context = ""
    if competitor_posts:
        lines = []
        for p in competitor_posts[:3]:
            lines.append(f'  - @{p["handle"]} ({p["post_date"][:10]}): "{p["caption_preview"]}"')
        competitor_context = "RECENT COMPETITOR POSTS ON THIS TOPIC:\n" + "\n".join(lines)
    else:
        competitor_context = "RECENT COMPETITOR POSTS ON THIS TOPIC: None found."

    example_signals = result.get("example_signals", [])
    signal_lines = "\n".join(f"  - [{s[0]}] {s[1]}" for s in example_signals[:5])

    related = result.get("related_topics", [])
    related_str = ", ".join(related) if related else "None"

    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are writing a content strategy brief for an Instagram creator in the AI/tech niche.
All facts below are pre-calculated from real data. Do not invent numbers, claims, or insights not present here.
Your only job is to write clear, direct, actionable prose using these facts.

DATE: {today}
CREATOR: @{handle}
NICHE: AI/Tech

--- SIGNAL DATA ---
TOP TOPIC TODAY: {topic}
SOURCES DETECTING THIS: {source_count}/5 ({sources})
CONFIDENCE SCORE: {confidence}/100

RECENT SIGNALS SUPPORTING THIS (these are the actual headlines/posts driving the trend):
{signal_lines}

ALSO TRENDING THIS CYCLE: {related_str}

COMPETITOR GAP: {gap_desc}

{competitor_context}

WINNING FORMAT THIS MONTH: {fmt_name} ({fmt_multiplier}x above baseline)
BEST POSTING TIME: {best_time_str}{f" or {second_time_str}" if second_time_str else ""}
--- END SIGNAL DATA ---

Write a brief with exactly these four sections. Each section heading must appear on its own line.

## What's Working Right Now
2-3 bullet points citing the exact numbers above. Tell the creator what is performing and why it matters.

## What to Avoid Today
1-2 bullets on oversaturated topics or formats to skip based on the data.

## Today's Recommendation
One clear recommendation. Include:
- Topic and specific angle (not generic — make it concrete for the AI/tech niche).
  Ground the angle in the actual headlines above: name the specific companies,
  products, people, or events they mention (e.g. an IPO filing, a model launch),
  and connect to the related trending topics where it sharpens the story.
- Format: {fmt_name}
- Posting time: {best_time_str}
- Opening caption line (write the actual first sentence, make it a hook)

## Why This Will Work
2-3 sentences explaining the logic using the signal data above. Reference real numbers.

Tone: direct, confident, like a strategist who has looked at the data and made a decision. No hedging. Under 400 words total.
"""
    return prompt.strip()
