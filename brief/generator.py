"""
Assembles pre-calculated facts, calls Groq API for prose, saves brief to DB.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from groq import Groq
from brief.template import build_prompt
from brief.pdf import render_pdf
from db import get_conn

load_dotenv()

MODEL = "llama-3.3-70b-versatile"


def generate(result: dict, dry_run: bool = False) -> dict:
    """
    result: output from analysis/scorer.py score_creator()
    Returns: {brief_text, pdf_path, brief_id}
    """
    prompt = build_prompt(result)

    if dry_run:
        print("\n--- PROMPT ---")
        print(prompt)
        print("\n--- DRY RUN: no API call ---")
        return {"brief_text": "[dry run]", "pdf_path": None, "brief_id": None}

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800,
    )
    brief_text = response.choices[0].message.content.strip()

    conn = get_conn()
    try:
        cursor = conn.execute(
            """SELECT id FROM creators WHERE handle = ?""",
            (result["handle"].lstrip("@"),),
        )
        creator_row = cursor.fetchone()
        creator_id = creator_row["id"] if creator_row else None

        pdf_path = render_pdf(result["handle"], brief_text, result, creator_id=creator_id)

        cur = conn.execute(
            """INSERT INTO briefs (creator_id, confidence_score, top_topic, pdf_path)
               VALUES (?, ?, ?, ?)""",
            (creator_id, result["confidence_score"], result["topic"], pdf_path),
        )
        brief_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    return {"brief_text": brief_text, "pdf_path": pdf_path, "brief_id": brief_id}


if __name__ == "__main__":
    import json
    dry = "--dry-run" in sys.argv
    handle = next((a for a in sys.argv[1:] if not a.startswith("--")), None)

    if not handle:
        print("Usage: python -m brief.generator <handle> [--dry-run]")
        sys.exit(1)

    from db import get_creator, get_competitors
    from analysis.scorer import score_creator

    creator = get_creator(handle)
    if not creator:
        print(f"Creator @{handle} not found in DB")
        sys.exit(1)

    creator["competitors"] = get_competitors(creator["id"])
    result = score_creator(creator)

    if result:
        out = generate(result, dry_run=dry)
        if not dry:
            print(f"\nBrief generated → {out['pdf_path']}")
            print("\n" + out["brief_text"])
    else:
        print("No brief generated (confidence below threshold)")
