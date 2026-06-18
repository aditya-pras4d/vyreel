"""
Renders the brief text to a clean PDF using WeasyPrint, following the Vyreel brand system.

Colors: #111214 (Graphite), #FAF7F1 (Warm Off-White), #00C6FF (Cyan), #FFE65A (Yellow), #B784FF (Violet), #A9B1A6 (Sage)
Fonts: Playfair Display (logo), Inter (UI), IBM Plex Mono (data/labels)
"""
import os
import re
from datetime import date

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "briefs")


def _md_to_html(text: str) -> str:
    lines = text.split("\n")
    html_lines = []
    in_ul = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("## "):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            heading = stripped[3:]
            html_lines.append(f'<h2>{heading}</h2>')

        elif stripped.startswith("- ") or stripped.startswith("• "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            content = stripped[2:]
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            content = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", content)
            html_lines.append(f"<li>{content}</li>")

        elif stripped == "":
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False

        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            content = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", content)
            html_lines.append(f"<p>{content}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def render_pdf(handle: str, brief_text: str, result: dict, creator_id=None) -> str:
    from weasyprint import HTML, CSS

    # Handles are validated at entry, but never trust input that becomes a filename
    handle_clean = re.sub(r"[^A-Za-z0-9._]", "_", handle.lstrip("@"))[:30]
    today = date.today()
    # Files are named by creator id (not handle) so no client name is exposed in output.
    ident = f"c{creator_id}" if creator_id is not None else handle_clean
    filename = f"brief_{ident}_{today.isoformat()}.pdf"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)

    topic = result.get("topic", "")
    confidence = int(result.get("confidence_score", 0) * 100)
    source_count = result.get("source_count", 0)
    sources = " · ".join(s.upper() for s in result.get("sources", []))
    winning_fmt = result.get("winning_format", {})
    fmt_name = winning_fmt.get("format", "—")
    fmt_mult = winning_fmt.get("multiplier", "—")
    best_times = result.get("best_times", [])
    best_time = best_times[0]["label"] if best_times else "—"
    gap_score = result.get("gap_score", 0)
    gap_label = "OPEN" if gap_score >= 1.0 else ("PARTIAL" if gap_score >= 0.5 else "SATURATED")
    gap_color = "#FFE65A" if gap_score >= 1.0 else ("#00C6FF" if gap_score >= 0.5 else "#A9B1A6")

    brief_html = _md_to_html(brief_text)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  @page {{
    size: A4;
    margin: 52px 56px;
    background: #111214;
  }}

  body {{
    font-family: 'Inter', -apple-system, sans-serif;
    background: #111214;
    color: #FAF7F1;
    font-size: 13px;
    line-height: 1.6;
  }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 40px;
    padding-bottom: 24px;
    border-bottom: 1px solid rgba(0, 198, 255, 0.2);
  }}

  .logo {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .logo-star-y {{ color: #FFE65A; font-size: 18px; }}
  .logo-text {{
    font-family: 'Playfair Display', serif;
    font-size: 22px;
    color: #FAF7F1;
    letter-spacing: -0.3px;
  }}
  .logo-star-v {{ color: #B784FF; font-size: 12px; margin-left: 2px; }}
  .logo-sub {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px;
    color: #A9B1A6;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-top: 4px;
  }}

  .header-meta {{ text-align: right; }}
  .header-handle {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    color: #00C6FF;
    margin-bottom: 3px;
  }}
  .header-date {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    color: #A9B1A6;
    letter-spacing: 0.5px;
  }}

  /* Signal bar */
  .signal-bar {{
    display: flex;
    gap: 12px;
    margin-bottom: 40px;
  }}

  .signal-box {{
    flex: 1;
    padding: 14px 16px;
    border: 1px solid rgba(169,177,166,0.12);
    border-radius: 2px;
  }}

  .signal-box.primary {{ border-color: rgba(0,198,255,0.25); }}
  .signal-box.discovery {{ border-color: rgba(255,230,90,0.2); }}
  .signal-box.intelligence {{ border-color: rgba(183,132,255,0.2); }}

  .signal-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 8px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #A9B1A6;
    margin-bottom: 6px;
  }}
  .signal-value {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 20px;
    font-weight: 500;
    line-height: 1;
    margin-bottom: 4px;
  }}
  .signal-value.cyan {{ color: #00C6FF; }}
  .signal-value.yellow {{ color: #FFE65A; }}
  .signal-value.violet {{ color: #B784FF; }}
  .signal-value.sm {{ font-size: 13px; padding-top: 3px; }}
  .signal-sub {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px;
    color: #A9B1A6;
    letter-spacing: 0.3px;
  }}

  /* Brief body */
  h2 {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    color: #00C6FF;
    margin: 28px 0 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(0,198,255,0.12);
  }}

  p {{
    margin-bottom: 8px;
    color: #FAF7F1;
    font-size: 13px;
    line-height: 1.65;
  }}

  ul {{
    padding-left: 0;
    margin-bottom: 8px;
    list-style: none;
  }}

  li {{
    color: #FAF7F1;
    font-size: 13px;
    line-height: 1.65;
    margin-bottom: 5px;
    padding-left: 16px;
    position: relative;
  }}

  li::before {{
    content: "◆";
    position: absolute;
    left: 0;
    color: #00C6FF;
    font-size: 6px;
    top: 6px;
  }}

  strong {{ color: #FFE65A; font-weight: 600; }}

  /* Footer */
  .footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid rgba(169,177,166,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .footer-left {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px;
    color: rgba(169,177,166,0.4);
    letter-spacing: 0.5px;
  }}

  .footer-right {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .confidence-bar-bg {{
    width: 80px;
    height: 3px;
    background: rgba(169,177,166,0.15);
    border-radius: 2px;
    overflow: hidden;
  }}
  .confidence-bar-fill {{
    height: 100%;
    width: {confidence}%;
    background: {'#FFE65A' if confidence >= 80 else '#00C6FF'};
    border-radius: 2px;
  }}
  .confidence-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px;
    color: {'#FFE65A' if confidence >= 80 else '#00C6FF'};
    letter-spacing: 0.5px;
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="logo">
      <span class="logo-star-y">✦</span>
      <span class="logo-text">Vyreel</span>
      <span class="logo-star-v">✦</span>
    </div>
    <div class="logo-sub">Content Intelligence Brief</div>
  </div>
  <div class="header-meta">
    <div class="header-handle">@{handle_clean}</div>
    <div class="header-date">{today.strftime("%d %b %Y").upper()}</div>
  </div>
</div>

<div class="signal-bar">
  <div class="signal-box primary">
    <div class="signal-label">Top Topic</div>
    <div class="signal-value cyan sm">{topic}</div>
    <div class="signal-sub">{source_count}/5 · {sources}</div>
  </div>
  <div class="signal-box discovery">
    <div class="signal-label">Confidence</div>
    <div class="signal-value yellow">{confidence}</div>
    <div class="signal-sub">out of 100</div>
  </div>
  <div class="signal-box intelligence">
    <div class="signal-label">Competitor Gap</div>
    <div class="signal-value sm" style="color:{gap_color};">{gap_label}</div>
    <div class="signal-sub">7-day window</div>
  </div>
  <div class="signal-box">
    <div class="signal-label">Best Format</div>
    <div class="signal-value cyan sm">{fmt_name}</div>
    <div class="signal-sub">{fmt_mult}× baseline</div>
  </div>
  <div class="signal-box">
    <div class="signal-label">Post Window</div>
    <div class="signal-value sm" style="color:#FAF7F1;font-size:11px;">{best_time}</div>
    <div class="signal-sub">peak engagement</div>
  </div>
</div>

{brief_html}

<div class="footer">
  <div class="footer-left">Vyreel · Pilot 2026 · Generated {today.strftime("%d %b %Y").upper()}</div>
  <div class="footer-right">
    <div class="confidence-bar-bg">
      <div class="confidence-bar-fill"></div>
    </div>
    <div class="confidence-label">{confidence}/100</div>
  </div>
</div>

</body>
</html>"""

    HTML(string=html).write_pdf(output_path)
    print(f"[pdf] written to {output_path}")
    return output_path
