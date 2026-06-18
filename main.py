"""
Vyreel CLI entrypoint.

Usage:
  python main.py init                          # initialise DB
  python main.py collect                       # run all collectors once
  python main.py backfill --handle @creator    # pull 90d Instagram history
  python main.py brief --handle @creator       # generate + send brief
  python main.py brief --handle @creator --dry-run  # print brief, no send
  python main.py brief --handle @creator --force    # ignore confidence threshold
  python main.py schedule                      # start the scheduler daemon
  python main.py onboard                       # start the onboarding web app
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()


def cmd_init():
    from db import init_db
    init_db()
    print("DB initialised.")


def cmd_collect():
    from collectors import reddit, news, youtube, trends
    from collectors.instagram import collect_recent_competitors, collect_hashtags
    reddit.collect()
    news.collect()
    youtube.collect()
    trends.collect()
    collect_recent_competitors()
    collect_hashtags()


def cmd_backfill(handle: str):
    from collectors.instagram import collect
    from db import get_creator, get_competitors
    creator = get_creator(handle)
    if not creator:
        print(f"Creator @{handle} not in DB. Add them via the onboarding form first.")
        sys.exit(1)
    competitors = get_competitors(creator["id"])
    collect(handle, max_posts=50, is_competitor=False)
    for comp in competitors:
        collect(comp, max_posts=50, is_competitor=True)
    print(f"Backfill complete for @{handle}")


def cmd_brief(handle: str, dry_run: bool = False, force: bool = False):
    from db import get_creator, get_competitors
    from analysis.scorer import score_creator, BRIEF_THRESHOLD
    from brief.generator import generate
    from delivery.email import send

    creator = get_creator(handle)
    if not creator:
        print(f"Creator @{handle} not found.")
        sys.exit(1)

    creator["competitors"] = get_competitors(creator["id"])
    # With --force, widen the window to 48h and keep the real computed score/gap
    # instead of fabricating zeros.
    result = score_creator(creator, ignore_threshold=force, hours_back=48 if force else 24)

    if not result:
        if force:
            print("No topics detected at all — nothing to generate.")
        else:
            print("No brief generated (below threshold). Use --force to override.")
        return

    if result.get("below_threshold"):
        print(f"--force: confidence {int(result['confidence_score']*100)}/100 is below the "
              f"send threshold, but generating brief with best available data.")

    out = generate(result, dry_run=dry_run)
    if dry_run:
        return

    print(f"\nBrief generated → {out['pdf_path']}")
    print("\n" + out["brief_text"])

    if not dry_run and out.get("brief_id") and out.get("pdf_path"):
        send(
            creator_email=creator["email"],
            handle=creator["handle"],
            brief_id=out["brief_id"],
            pdf_path=out["pdf_path"],
            topic=result["topic"],
        )


def cmd_schedule():
    from scheduler import start
    start()


def cmd_onboard():
    from db import init_db
    init_db()
    from onboarding.app import app
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5050")),
    )


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]

    if cmd == "init":
        cmd_init()

    elif cmd == "collect":
        cmd_collect()

    elif cmd == "backfill":
        # Accept both `backfill --handle @foo` and `backfill @foo`
        handle = None
        if "--handle" in args:
            idx = args.index("--handle")
            if idx + 1 < len(args):
                handle = args[idx + 1]
        else:
            handle = next((a for a in args[1:] if not a.startswith("--")), None)
        if not handle:
            print("Usage: python main.py backfill --handle @creator")
            sys.exit(1)
        cmd_backfill(handle.strip().lstrip("@"))

    elif cmd == "brief":
        handle = None
        if "--handle" in args:
            idx = args.index("--handle")
            handle = args[idx + 1].lstrip("@")
        dry_run = "--dry-run" in args
        force = "--force" in args
        if not handle:
            print("Usage: python main.py brief --handle @creator [--dry-run] [--force]")
            sys.exit(1)
        cmd_brief(handle, dry_run=dry_run, force=force)

    elif cmd == "schedule":
        cmd_schedule()

    elif cmd == "onboard":
        cmd_onboard()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
