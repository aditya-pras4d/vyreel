"""
Combines topic detection, competitor gap, and trend velocity into a confidence score.
Score >= 0.65 → generate brief. Below → skip.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from analysis.topic_detector import detect
from analysis.competitor_gap import analyse
from analysis.engagement import get_winning_format
from analysis.timing import get_best_times

BRIEF_THRESHOLD = 0.65

# Broad "umbrella" topics make for vague briefs ("post about LLMs"). We demote them
# so concrete, specific topics (named products/companies/people/sharp trends) win when
# the signal is comparable. A topic doesn't have to be a company — just specific.
UMBRELLA_TOPICS = {
    "LLMs",
    "AI Agents",
    "AI Automation",
    "AI Video",
    "AI Image Generation",
    "No-code AI",
    "RAG",
    "Fine-tuning",
    "Prompt Engineering",
}
UMBRELLA_PENALTY = 0.6  # multiplier applied to an umbrella topic's confidence


def score_creator(creator: dict, ignore_threshold: bool = False, hours_back: int = 24) -> dict | None:
    """
    Runs full analysis for one creator.
    Returns a result dict if confidence >= threshold, else None.

    If ignore_threshold=True (used by `brief --force`), returns the best-scored
    result regardless of threshold — with the REAL computed confidence and gap
    score — as long as at least one topic was detected.
    """
    handle = creator["handle"].lstrip("@")
    competitors = creator.get("competitors", [])
    timezone = creator.get("timezone", "Asia/Kolkata")

    topics = detect(hours_back=hours_back)
    if not topics:
        print(f"[scorer] @{handle}: no topics detected")
        return None

    best_result = None
    best_score = 0.0

    for topic_data in topics[:10]:
        topic = topic_data["topic"]
        source_count = topic_data["source_count"]

        gap_data = analyse(topic, competitors)
        gap_score = gap_data["gap_score"]

        # Trend velocity: normalised source_count / 5 sources max
        source_score = source_count / 5.0

        # Simple trend velocity from total_signal (normalised, capped at 1.0)
        trend_velocity = min(topic_data["total_signal"] / 10000, 1.0)

        confidence = (source_score * 0.4) + (gap_score * 0.4) + (trend_velocity * 0.2)
        if topic in UMBRELLA_TOPICS:
            confidence *= UMBRELLA_PENALTY
        confidence = round(confidence, 3)

        if confidence > best_score:
            best_score = confidence
            best_result = {
                "topic": topic,
                "confidence_score": confidence,
                "source_count": source_count,
                "sources": topic_data["sources"],
                "gap_score": gap_score,
                "covered_by": gap_data["covered_by"],
                "competitor_posts": gap_data["competitor_posts"],
                "example_signals": topic_data["signals"],
            }

    if best_result is None:
        print(f"[scorer] @{handle}: no scorable topic")
        return None

    below = best_score < BRIEF_THRESHOLD
    if below and not ignore_threshold:
        print(f"[scorer] @{handle}: best score {best_score:.2f} below threshold {BRIEF_THRESHOLD}, no brief")
        return None

    winning_format = get_winning_format(handle)
    best_times = get_best_times(handle, timezone)

    # Other topics trending in the same cycle — gives the brief context to connect
    # the winning topic to related players/events (e.g. Anthropic ↔ OpenAI's IPO).
    related_topics = [t["topic"] for t in topics if t["topic"] != best_result["topic"]][:4]

    best_result.update({
        "handle": handle,
        "winning_format": winning_format,
        "best_times": best_times,
        "below_threshold": below,
        "related_topics": related_topics,
    })

    flag = " (below threshold, --force)" if below else " ✓"
    print(f"[scorer] @{handle}: topic='{best_result['topic']}' confidence={best_score:.2f}{flag}")
    return best_result


if __name__ == "__main__":
    import sys
    from db import get_creator, get_competitors, get_all_creators

    handle = sys.argv[1] if len(sys.argv) > 1 else None
    if handle:
        c = get_creator(handle)
        if c:
            c["competitors"] = get_competitors(c["id"])
            result = score_creator(c)
            print(result)
    else:
        for c in get_all_creators():
            c["competitors"] = get_competitors(c["id"])
            score_creator(c)
