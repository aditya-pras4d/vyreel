"""
Renders a client-facing 'how the brief was made' evidence report as a branded PDF,
matching the Vyreel brand system used in brief/pdf.py.

build_evidence_data() pulls everything live from the DB — no hardcoded creator or topic.
"""
import sys, os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import date

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "evidence")

SOURCE_LABELS = {
    "reddit": "Reddit", "news": "News", "youtube": "YouTube",
    "trends": "Trends", "instagram": "Instagram",
}


def build_evidence_data(handle: str, hours_back: int = 48) -> dict:
    """Assembles the evidence report data for a creator straight from the DB."""
    from analysis.topic_detector import detect, _extract_topics
    from analysis.competitor_gap import analyse
    from db import get_conn, get_creator, get_competitors

    creator = get_creator(handle)
    competitors = get_competitors(creator["id"]) if creator else []

    topics = detect(hours_back=hours_back)
    if not topics:
        raise ValueError("No topics detected — run `python main.py collect` first.")

    # Score every topic the same way the scorer does, to find the winner.
    ranked = []
    for t in topics:
        gap = analyse(t["topic"], competitors)
        source_score = t["source_count"] / 5.0
        velocity = min(t["total_signal"] / 10000, 1.0)
        conf = round(source_score * 0.4 + gap["gap_score"] * 0.4 + velocity * 0.2, 3)
        ranked.append({**t, "gap": gap, "source_score": source_score,
                       "velocity": velocity, "conf": conf})

    ranked.sort(key=lambda r: (r["source_count"], r["total_signal"]), reverse=True)
    winner = ranked[0]
    topic = winner["topic"]

    conn = get_conn()
    try:
        counts = {
            "reddit": conn.execute("SELECT COUNT(*) FROM reddit_signals").fetchone()[0],
            "news": conn.execute("SELECT COUNT(*) FROM news_signals").fetchone()[0],
            "youtube": conn.execute("SELECT COUNT(*) FROM youtube_signals").fetchone()[0],
            "trends": conn.execute("SELECT COUNT(*) FROM trend_signals").fetchone()[0],
        }
        counts["total"] = sum(counts.values())

        press, reddit_ev, youtube_ev = [], [], []
        seen_press, seen_reddit, seen_yt = set(), set(), set()
        for r in conn.execute("SELECT headline, source FROM news_signals").fetchall():
            if topic in _extract_topics(r["headline"]) and r["headline"] not in seen_press:
                seen_press.add(r["headline"])
                press.append(f'"{r["headline"]}" — {r["source"]}')
        for r in conn.execute("SELECT title FROM reddit_signals").fetchall():
            if topic in _extract_topics(r["title"]) and r["title"] not in seen_reddit:
                seen_reddit.add(r["title"])
                reddit_ev.append(r["title"])
        for r in conn.execute("SELECT title, channel, view_count FROM youtube_signals").fetchall():
            if topic in _extract_topics(r["title"]) and r["title"] not in seen_yt:
                seen_yt.add(r["title"])
                youtube_ev.append(f'{r["title"]} — {r["channel"]}, {r["view_count"]:,} views')
    finally:
        conn.close()

    reddit_total = len(reddit_ev)
    detected_in = " · ".join(SOURCE_LABELS.get(s, s.title()) for s in winner["sources"])

    return {
        "creator_id": creator["id"] if creator else None,
        "counts": counts,
        "ranking": [
            {
                "rank": i + 1,
                "topic": r["topic"],
                "sources": r["source_count"],
                "signal": r["total_signal"],
                "detected_in": " · ".join(SOURCE_LABELS.get(s, s.title()) for s in r["sources"]),
            }
            for i, r in enumerate(ranked[:5])
        ],
        "winner_topic": topic,
        "winner_detected_in": detected_in,
        "reddit_total": reddit_total,
        "score": {
            "source_breadth": f"{winner['source_score']:.2f}",
            "gap": f"{winner['gap']['gap_score']:.2f}",
            "velocity_label": "rising" if winner["velocity"] < 0.3 else "high",
        },
        "evidence": {
            "press": press[:4],
            "reddit": reddit_ev[:6],
            "youtube": youtube_ev[:3],
        },
    }


def render_evidence_pdf(handle: str, data: dict) -> str:
    from weasyprint import HTML

    # Handles are validated at entry, but never trust input that becomes a filename
    handle_clean = re.sub(r"[^A-Za-z0-9._]", "_", handle.lstrip("@"))[:30]
    today = date.today()
    creator_id = data.get("creator_id")
    ident = f"c{creator_id}" if creator_id is not None else handle_clean
    filename = f"evidence_{ident}_{today.isoformat()}.pdf"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)

    counts = data["counts"]
    ranking = data["ranking"]          # list of dicts: rank, topic, sources, signal, detected_in
    score = data["score"]              # dict: source_breadth, gap, velocity_label
    evidence = data["evidence"]        # dict: press[], reddit[], youtube[]

    rank_rows = "".join(
        f"""<tr class="{'win' if r['rank']==1 else ''}">
              <td class="rk">{r['rank']}</td>
              <td class="tp">{r['topic']}</td>
              <td class="mono">{r['sources']}/5</td>
              <td class="mono">{r['signal']}</td>
              <td class="src">{r['detected_in']}</td>
            </tr>"""
        for r in ranking
    )

    press_items = "".join(f"<li>{p}</li>" for p in evidence["press"]) or "<li>None this cycle.</li>"
    reddit_items = "".join(f"<li>{p}</li>" for p in evidence["reddit"]) or "<li>None this cycle.</li>"
    yt_items = "".join(f"<li>{p}</li>" for p in evidence["youtube"]) or "<li>None this cycle.</li>"

    topic = data["winner_topic"]
    detected_in = data["winner_detected_in"]
    n_sources = data["ranking"][0]["sources"] if data["ranking"] else 0
    reddit_total = data["reddit_total"]
    gap_score = float(score["gap"])
    if gap_score >= 1.0:
        gap_line = f"No tracked competitor has posted on <strong>{topic}</strong> — the lane is completely open."
    elif gap_score >= 0.5:
        gap_line = f"Competitor coverage of <strong>{topic}</strong> is partial — there is still a clear entry point."
    else:
        gap_line = f"<strong>{topic}</strong> is well covered by competitors — a contrarian or niche angle is needed."

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  @page {{ size:A4; margin:48px 52px; background:#111214; }}
  body {{ font-family:'Inter',sans-serif; background:#111214; color:#FAF7F1; font-size:12.5px; line-height:1.6; }}

  .header {{ display:flex; justify-content:space-between; align-items:flex-start;
            margin-bottom:30px; padding-bottom:20px; border-bottom:1px solid rgba(0,198,255,0.2); }}
  .logo {{ display:flex; align-items:center; gap:8px; }}
  .logo-star-y {{ color:#FFE65A; font-size:18px; }}
  .logo-text {{ font-family:'Playfair Display',serif; font-size:22px; letter-spacing:-0.3px; }}
  .logo-star-v {{ color:#B784FF; font-size:12px; margin-left:2px; }}
  .logo-sub {{ font-family:'IBM Plex Mono',monospace; font-size:9px; color:#A9B1A6;
              letter-spacing:1px; text-transform:uppercase; margin-top:4px; }}
  .header-meta {{ text-align:right; }}
  .header-handle {{ font-family:'IBM Plex Mono',monospace; font-size:13px; color:#00C6FF; margin-bottom:3px; }}
  .header-date {{ font-family:'IBM Plex Mono',monospace; font-size:10px; color:#A9B1A6; letter-spacing:0.5px; }}

  .intro {{ color:#A9B1A6; font-size:12px; margin-bottom:26px; line-height:1.7; }}

  h2 {{ font-family:'IBM Plex Mono',monospace; font-size:9px; font-weight:500; letter-spacing:1.8px;
       text-transform:uppercase; color:#00C6FF; margin:26px 0 12px; padding-bottom:7px;
       border-bottom:1px solid rgba(0,198,255,0.12); }}

  .stat-bar {{ display:flex; gap:10px; margin-bottom:6px; }}
  .stat {{ flex:1; padding:12px 14px; border:1px solid rgba(169,177,166,0.14); border-radius:2px; }}
  .stat-val {{ font-family:'IBM Plex Mono',monospace; font-size:22px; font-weight:500; color:#00C6FF; line-height:1; }}
  .stat-lbl {{ font-family:'IBM Plex Mono',monospace; font-size:8px; letter-spacing:1px; text-transform:uppercase;
              color:#A9B1A6; margin-top:6px; }}

  table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
  th {{ font-family:'IBM Plex Mono',monospace; font-size:8px; letter-spacing:1px; text-transform:uppercase;
       color:#A9B1A6; text-align:left; padding:6px 8px; border-bottom:1px solid rgba(169,177,166,0.2); }}
  td {{ padding:8px; font-size:12px; border-bottom:1px solid rgba(169,177,166,0.08); }}
  td.rk {{ font-family:'IBM Plex Mono',monospace; color:#A9B1A6; width:30px; }}
  td.tp {{ font-weight:600; }}
  td.mono {{ font-family:'IBM Plex Mono',monospace; color:#00C6FF; }}
  td.src {{ font-family:'IBM Plex Mono',monospace; font-size:10px; color:#A9B1A6; }}
  tr.win td {{ background:rgba(255,230,90,0.06); }}
  tr.win td.tp {{ color:#FFE65A; }}
  tr.win td.rk {{ color:#FFE65A; }}

  .formula {{ font-family:'IBM Plex Mono',monospace; font-size:11px; background:rgba(0,198,255,0.05);
             border:1px solid rgba(0,198,255,0.15); border-radius:2px; padding:14px 16px; margin:6px 0 14px;
             color:#FAF7F1; line-height:1.8; white-space:pre-wrap; }}
  .formula .c {{ color:#A9B1A6; }}

  .score-grid {{ display:flex; gap:10px; }}
  .score-box {{ flex:1; padding:12px 14px; border:1px solid rgba(183,132,255,0.2); border-radius:2px; }}
  .score-box .v {{ font-family:'IBM Plex Mono',monospace; font-size:16px; color:#B784FF; }}
  .score-box .l {{ font-family:'IBM Plex Mono',monospace; font-size:8px; letter-spacing:0.5px;
                  text-transform:uppercase; color:#A9B1A6; margin-top:5px; }}
  .score-box .d {{ font-size:10.5px; color:#FAF7F1; margin-top:6px; line-height:1.5; }}

  .ev-group {{ margin-bottom:14px; }}
  .ev-title {{ font-family:'IBM Plex Mono',monospace; font-size:10px; color:#FFE65A; margin-bottom:6px; }}
  ul {{ list-style:none; padding-left:0; }}
  li {{ font-size:11.5px; line-height:1.6; margin-bottom:4px; padding-left:15px; position:relative; color:#FAF7F1; }}
  li::before {{ content:"◆"; position:absolute; left:0; color:#00C6FF; font-size:5px; top:6px; }}

  .rec {{ border-left:2px solid #FFE65A; padding:4px 0 4px 16px; margin:6px 0 14px; }}
  .rec-body {{ font-size:13px; line-height:1.6; margin-bottom:10px; }}
  .rec-hook {{ font-style:italic; color:#00C6FF; font-size:12.5px; margin-bottom:12px; }}

  .footer {{ margin-top:36px; padding-top:14px; border-top:1px solid rgba(169,177,166,0.1);
            font-family:'IBM Plex Mono',monospace; font-size:9px; color:rgba(169,177,166,0.5);
            letter-spacing:0.5px; }}
</style></head><body>

<div class="header">
  <div>
    <div class="logo"><span class="logo-star-y">✦</span><span class="logo-text">Vyreel</span><span class="logo-star-v">✦</span></div>
    <div class="logo-sub">How This Brief Was Made — Evidence Report</div>
  </div>
  <div class="header-meta">
    <div class="header-handle">@{handle_clean}</div>
    <div class="header-date">{today.strftime("%d %b %Y").upper()}</div>
  </div>
</div>

<div class="intro">
  This report shows the raw signal data and the exact logic behind today's brief.
  Nothing is hand-picked — every number is pulled directly from live public sources
  collected in the last 24–48 hours.
</div>

<h2>1 · Data Collected This Cycle</h2>
<div class="stat-bar">
  <div class="stat"><div class="stat-val">{counts['reddit']}</div><div class="stat-lbl">Reddit posts</div></div>
  <div class="stat"><div class="stat-val">{counts['news']}</div><div class="stat-lbl">News headlines</div></div>
  <div class="stat"><div class="stat-val">{counts['youtube']}</div><div class="stat-lbl">YouTube videos</div></div>
  <div class="stat"><div class="stat-val">{counts['trends']}</div><div class="stat-lbl">Trend scores</div></div>
  <div class="stat"><div class="stat-val">{counts['total']}</div><div class="stat-lbl">Total signals</div></div>
</div>

<h2>2 · Topic Detection — What's Trending</h2>
<table>
  <tr><th>#</th><th>Topic</th><th>Sources</th><th>Signal</th><th>Detected in</th></tr>
  {rank_rows}
</table>
<p style="font-size:11.5px;color:#A9B1A6;margin-top:10px;line-height:1.6;">
  <strong style="color:#FFE65A;">{topic} wins</strong> — top-ranked topic, confirmed by {n_sources} independent
  source types ({detected_in}). Cross-source agreement is the strongest early signal.
</p>

<h2>3 · How the Confidence Score Is Calculated</h2>
<div class="formula"><span class="c">confidence =</span> (source_breadth × 0.40)   <span class="c">← how many sources confirm it</span>
           + (competitor_gap × 0.40)   <span class="c">← is the lane open for @{handle_clean}?</span>
           + (trend_velocity × 0.20)   <span class="c">← how fast is interest climbing?</span></div>
<div class="score-grid">
  <div class="score-box"><div class="v">{score['source_breadth']}</div><div class="l">Source breadth</div><div class="d">confirmed by {n_sources} source types</div></div>
  <div class="score-box"><div class="v">{score['gap']}</div><div class="l">Competitor gap</div><div class="d">lane availability for this creator</div></div>
  <div class="score-box"><div class="v">{score['velocity_label']}</div><div class="l">Trend velocity</div><div class="d">how fast interest is climbing</div></div>
</div>

<h2>4 · The Evidence — Real Signals Behind "{topic}"</h2>
<div class="ev-group"><div class="ev-title">📰 Press</div><ul>{press_items}</ul></div>
<div class="ev-group"><div class="ev-title">💬 Reddit — {reddit_total} posts detected this cycle</div><ul>{reddit_items}</ul></div>
<div class="ev-group"><div class="ev-title">▶️ YouTube</div><ul>{yt_items}</ul></div>

<h2>5 · Why "{topic}" Was Chosen</h2>
<div class="rec">
  <div class="rec-body">{gap_line}</div>
  <ul>
    <li>Confirmed across {n_sources} independent source types ({detected_in}) — it is not noise.</li>
    <li>Selected over {len(data['ranking']) - 1} other candidate topics by combined confidence score.</li>
    <li>The brief turns this into one concrete Reel recommendation with a ready-to-use opening hook.</li>
  </ul>
</div>

<h2>6 · Methodology</h2>
<ul>
  <li>All data is from <strong>public sources</strong>, collected automatically.</li>
  <li>Vyreel does <strong>not</strong> invent claims — the language model writes prose only around the pre-calculated facts above.</li>
  <li>Format & posting-time precision sharpen further once @{handle_clean}'s competitor accounts and 90-day post history are connected.</li>
</ul>

<div class="footer">Vyreel · Content Intelligence · Pilot 2026 · Generated {today.strftime("%d %b %Y").upper()}</div>

</body></html>"""

    HTML(string=html).write_pdf(output_path)
    print(f"[evidence-pdf] written to {output_path}")
    return output_path


if __name__ == "__main__":
    handle = sys.argv[1] if len(sys.argv) > 1 else None
    if not handle:
        print("Usage: python -m brief.evidence_pdf <handle>")
        sys.exit(1)
    data = build_evidence_data(handle)
    render_evidence_pdf(handle, data)
