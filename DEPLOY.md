# Deploy the Vyreel waitlist

A Flask + SQLite app. Deploys to **Render** from GitHub. ~10 minutes.

## What goes live
- `/waitlist` — the working waitlist form (saves signups to SQLite)
- `/style-preview` — the kraft / paper-cutout design mockup (visual only, not wired to the DB)

---

## 1. Push the code to GitHub
Run from the project root (`/Users/adityaprasad/Desktop/ADI/vyreel`):

```bash
git init
git add .
git commit -m "Vyreel waitlist"
git branch -M main
git remote add origin https://github.com/<your-username>/vyreel.git
git push -u origin main
```

> `.gitignore` already excludes `.env` and `*.db`, so secrets and the local
> database are NOT uploaded — the server starts with a fresh DB.
> If `git push` asks for a password, use a GitHub Personal Access Token
> (github.com → Settings → Developer settings → Tokens).

## 2. Create the Render web service
1. render.com → sign up with GitHub → **New +** → **Web Service** → pick the `vyreel` repo.
2. Settings:
   - **Build Command:** `pip install -r requirements-web.txt`
   - **Start Command:** `gunicorn onboarding.app:app --workers 1 --bind 0.0.0.0:$PORT`
   - **Instance Type:** Free
3. **Environment variables** (Advanced → Add):
   - `FLASK_SECRET` = `7895c93e0af08a7665d6503927d415438594621e865bacf68d5a1e6228242aca`
   - `VYREEL_DB_PATH` = `/var/data/vyreel.db`
   - `PYTHON_VERSION` = `3.12.7`
4. **Create Web Service.**

## 3. Make signups persist (do this, or data is wiped on every redeploy)
In the service → **Disks** → **Add Disk**:
- Name: `data`
- Mount Path: `/var/data`
- Size: 1 GB

(This matches `VYREEL_DB_PATH`, so the SQLite file lives on the persistent disk.)

## 4. Visit
Render gives a URL like `https://vyreel.onrender.com`:
- Waitlist: `https://vyreel.onrender.com/waitlist`
- Design preview: `https://vyreel.onrender.com/style-preview`

> Free instances sleep after ~15 min idle; first hit takes ~30s to wake.

## 5. Read signups later
Service → **Shell** tab:
```bash
python -c "import db; [print(r['email'], r['handle'], r['niche'], r['about']) for r in db.get_waitlist()]"
```

---

### Notes
- Rate limiting is in-memory, hence `--workers 1`. Fine for a waitlist.
- The 3 creator images in `onboarding/static/` are ~2 MB each — consider
  compressing before launch so the page isn't ~6 MB to load.
- The kraft design at `/style-preview` is a mockup; its form does not submit.
