import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import re
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from db import (
    init_db,
    add_creator,
    get_creator,
    valid_handle,
    normalize_phone,
    valid_email,
    add_to_waitlist,
    get_waitlist_count,
    AlreadyOnWaitlistError,
)

app = Flask(__name__)

_secret = os.environ.get("FLASK_SECRET")
if not _secret:
    raise RuntimeError(
        "FLASK_SECRET is not set. Refusing to start with a guessable session key — "
        "set it in .env or the environment."
    )
app.secret_key = _secret

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["120 per hour"],
    storage_uri="memory://",
)

# Ensure DB tables exist regardless of how the app is launched
with app.app_context():
    init_db()

TIMEZONES = [
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Singapore",
    "Europe/London",
    "Europe/Paris",
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "Australia/Sydney",
    "Pacific/Auckland",
]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

NICHES = [
    "AI / Tech",
    "Finance / Investing",
    "Business / Entrepreneurship",
    "Fitness / Health",
    "Food / Cooking",
    "Fashion / Beauty",
    "Travel",
    "Gaming",
    "Education",
    "Comedy / Entertainment",
    "Lifestyle",
    "Other",
]


@app.route("/", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def index():
    error = None
    if request.method == "POST":
        handle = request.form.get("handle", "").strip().lstrip("@")
        email = request.form.get("email", "").strip()
        phone_raw = request.form.get("phone", "").strip()
        timezone = request.form.get("timezone", "Asia/Kolkata")
        phone = normalize_phone(phone_raw)

        if not valid_handle(handle):
            error = "That doesn't look like a valid Instagram handle (letters, numbers, dots, underscores)."
        elif not phone:
            error = "A WhatsApp number with country code is required, e.g. +91 98765 43210."
        elif timezone not in TIMEZONES:
            error = "Please pick a timezone from the list."
        elif not EMAIL_RE.match(email):
            error = "A valid email is required — that's where your daily brief is delivered."
        elif get_creator(handle):
            error = f"@{handle} is already registered."
        else:
            session["pending"] = {
                "handle": handle,
                "email": email,
                # keep the '+' so add_creator's own validation accepts it
                "phone": f"+{phone}",
                "timezone": timezone,
            }
            return redirect(url_for("competitors"))

    return render_template("index.html", timezones=TIMEZONES, error=error)


@app.route("/competitors", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def competitors():
    pending = session.get("pending")
    if not pending:
        return redirect(url_for("index"))

    if request.method == "POST":
        comps = []
        for i in range(1, 6):
            c = request.form.get(f"competitor_{i}", "").strip().lstrip("@")
            if not c:
                continue
            if not valid_handle(c):
                return render_template(
                    "competitors.html",
                    handle=pending["handle"],
                    error=f"@{c} is not a valid Instagram handle.",
                )
            comps.append(c)

        try:
            add_creator(
                handle=pending["handle"],
                email=pending["email"],
                phone=pending["phone"],
                timezone=pending["timezone"],
                competitors=comps,
            )
        except ValueError as e:
            session.pop("pending", None)
            return render_template("index.html", timezones=TIMEZONES, error=str(e))

        session.pop("pending", None)
        session["created_handle"] = pending["handle"]
        return redirect(url_for("success"))

    return render_template("competitors.html", handle=pending["handle"], error=None)


@app.route("/success")
def success():
    handle = session.pop("created_handle", "")
    return render_template("success.html", handle=handle)


@app.route("/waitlist", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def waitlist():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        handle = request.form.get("handle", "").strip().lstrip("@")
        name = request.form.get("name", "").strip()
        niche = request.form.get("niche", "").strip()
        about = request.form.get("about", "").strip()  # optional

        if not valid_email(email):
            error = "Please enter a valid email so we can reach you when a spot opens."
        elif not valid_handle(handle):
            error = "An Instagram handle is required (letters, numbers, dots, underscores)."
        elif not name:
            error = "Please tell us your name."
        elif niche not in NICHES:
            error = "Please pick a niche from the list."
        else:
            try:
                _id, position = add_to_waitlist(
                    email=email, handle=handle, name=name, niche=niche, about=about
                )
            except AlreadyOnWaitlistError:
                # Friendly, not an error: they're already in.
                return render_template(
                    "waitlist_success.html", position=None, already=True
                )
            except ValueError as e:
                return render_template("waitlist.html", niches=NICHES, error=str(e))
            return render_template(
                "waitlist_success.html", position=position, already=False
            )

    return render_template("waitlist.html", niches=NICHES, error=error)


@app.route("/style-preview")
def style_preview():
    # Visual-only mockup of the kraft / paper-cutout aesthetic. Not wired to the
    # DB so the live /waitlist is untouched while we compare directions.
    return render_template("style_preview.html", niches=NICHES)


@app.route("/mockup")
def mockup():
    return render_template("mockup.html")


if __name__ == "__main__":
    init_db()
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5050")),
    )
