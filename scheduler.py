"""
APScheduler job runner.
- Collectors run every 6 hours
- Brief generation runs hourly: each creator gets their brief when it's
  6am in THEIR timezone (deduped so they get at most one brief per day)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import traceback
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from db import init_db, get_all_creators, get_competitors, get_conn
from collectors import reddit, news, youtube, trends
from collectors.instagram import collect_recent_competitors
from analysis.scorer import score_creator
from brief.generator import generate
from delivery.email import send

scheduler = BlockingScheduler()

BRIEF_HOUR = 6  # creator-local hour to deliver the daily brief


def run_collectors():
    print("[scheduler] running collectors")
    for collector in (reddit.collect, news.collect, youtube.collect, trends.collect,
                      collect_recent_competitors):
        try:
            collector()
        except Exception:
            print(f"[scheduler] collector {collector.__name__} failed:\n{traceback.format_exc()}")


def _brief_generated_today(creator_id: int) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM briefs WHERE creator_id = ? AND date(generated_at) = date('now') LIMIT 1",
            (creator_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def run_briefs():
    now_utc = datetime.now(timezone.utc)
    for creator in get_all_creators():
        try:
            tz = pytz.timezone(creator.get("timezone") or "Asia/Kolkata")
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone("Asia/Kolkata")

        if now_utc.astimezone(tz).hour != BRIEF_HOUR:
            continue
        if _brief_generated_today(creator["id"]):
            continue

        print(f"[scheduler] brief for @{creator['handle']} (6am {tz.zone})")
        creator["competitors"] = get_competitors(creator["id"])
        try:
            result = score_creator(creator)
            if result:
                out = generate(result)
                if out["pdf_path"]:
                    send(
                        creator_email=creator["email"],
                        handle=creator["handle"],
                        brief_id=out["brief_id"],
                        pdf_path=out["pdf_path"],
                        topic=result["topic"],
                    )
        except Exception:
            print(f"[scheduler] error for @{creator['handle']}:\n{traceback.format_exc()}")


def start():
    init_db()

    # Collectors: every 6 hours
    scheduler.add_job(run_collectors, "interval", hours=6, id="collectors")

    # Briefs: check hourly which creators just hit 6am local time.
    # Fires at :35 past the hour so half-hour timezones (IST = UTC+5:30) are
    # caught within their 6am hour.
    scheduler.add_job(run_briefs, CronTrigger(minute=35), id="briefs")

    print(f"[scheduler] starting — collectors every 6h, briefs at {BRIEF_HOUR}am per creator timezone")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("[scheduler] stopped")


if __name__ == "__main__":
    start()
