# Watchtower — Website Change Detector

Watchtower monitors public web pages and records meaningful content changes while filtering common page noise. The existing React dashboard is preserved.

## Requirements
- Python 3.11+ recommended
- Node.js 18+
- Playwright Chromium browser

## Run the backend (Windows PowerShell)
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

## Run the frontend
In another terminal:
```powershell
cd frontend
npm install
npm run dev
```
Open the Vite URL printed in the terminal (usually http://localhost:5173).

## Configuration
Edit `backend/.env` locally. Do not commit it. Start with `.env.example`. Useful settings include `DEMO_MODE`, `SCHEDULER_ENABLED`, `DISCORD_WEBHOOK_URL`, `MAX_CONCURRENT_CHECKS`, and `PAGE_TIMEOUT_SECONDS`. Configure a Discord webhook only if you want notifications. The webhook is a secret and must never be shared or committed.

## Features
- Monitor creation, editing, pause/resume and manual checks
- Scheduled checks with bounded worker concurrency
- Playwright page rendering, screenshots and normalized text snapshots
- Content hashing so unchanged pages do not create duplicate versions
- Text diff/history, sensitivity/focus filtering, visual CSS-region picker (watch/ignore), and notification deduplication
- Public URL validation, failure status, retry-safe notification delivery and Discord alerts
- Demo data for trying the dashboard

## Visual region picker
In Add monitor or Edit, enter a public URL and choose **Choose regions visually**. Watchtower fetches a script-free static snapshot through the backend. Click elements to save CSS selectors under **Watch** (green) or **Ignore** (orange), then click Done and save the monitor. Watched selectors limit the text compared on each check; ignored selectors are removed before extraction. Selectors are saved with the monitor and returned by the API. Since the preview is static and scripts/forms are disabled, highly dynamic pages may look different from the live site.

## Important limitations
- This is a local prototype. Do not expose it directly to the public internet without authentication, deployment hardening, and a persistent production database.
- Screenshot snapshots are saved and shown in history. A pixel-highlighted screenshot-diff overlay remains a frontend follow-up; use the saved before/after images and text diff/history.
- Discord, SMTP email, and Telegram notifications are supported. The `/api/digest?hours=24` endpoint returns a digest payload that can be scheduled with Task Scheduler/cron; a built-in timed digest sender is not yet enabled.
- Public-only URL checks reduce SSRF risk but should be combined with network-level egress restrictions in production to defend against DNS rebinding and unusual routing.


## Deploy the complete app (Render)

The deployment uses one Docker-based Render web service for both the existing React dashboard and FastAPI/Playwright backend. This avoids a separate frontend URL and keeps `/api` and `/screenshots` same-origin. The Dockerfile builds the current frontend; it does not replace the UI or project features.

1. Push this project to a GitHub repository, including `Dockerfile` and `render.yaml`.
2. In Render, choose **New → Blueprint** and select that repository. Render reads `render.yaml` and builds the Docker image.
3. Keep the persistent disk mounted at `/var/data`; the SQLite database and screenshots are stored there so they survive service restarts/deploys. Persistent disks may require a paid Render instance.
4. When deployment finishes, open the service URL shown by Render. Check `https://YOUR-SERVICE.onrender.com/api/health` returns `{"status":"ok"}` and then open the base URL for the dashboard.
5. If you use notification links, set `PUBLIC_DASHBOARD_URL` in Render to the deployed service URL (without a trailing slash). Add any notification secrets in Render's Environment settings, not in GitHub.

The live URL does not exist until you create the Render service, so add the actual URL to this README after deployment. Never put webhook tokens, SMTP passwords, or bot tokens in the repository. For a fresh public deployment, keep `DEMO_MODE=false`; enable it only if you want sample data in a clean database.

### Deploy troubleshooting
- If the build fails, inspect the Render build logs; the Docker build installs the frontend dependencies and Playwright Chromium.
- If the service starts but health checks fail, inspect the Render runtime logs and confirm `/api/health` works.
- Without a persistent disk, local SQLite data and screenshots can be lost when the container is replaced. Do not remove the `/var/data` disk configuration if you want them persisted.

## Tests
```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest
```


## New reliability settings
- `sensitivity`: 1 (strict), 2 (balanced), 3 (high-signal) per monitor.
- Fetches retry up to `FETCH_RETRY_ATTEMPTS` with bounded backoff, identify common CAPTCHA/anti-bot interstitials, share identical URL/selector fetches for a short cache window, and throttle requests per domain.
- Email: set SMTP variables in `.env`, then enable `EMAIL_ENABLED=true`; per-monitor email toggles are stored on the monitor.
- Telegram: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; enable per monitor.
- Digest data: `GET /api/digest?hours=24`. For a daily digest, schedule a request to this endpoint and route the result through your preferred mail/chat workflow. Keep `.env` secrets private.

## Important implementation notes
The app is a local prototype. SMTP and Telegram delivery require valid server-side credentials. SQLite auto-migration adds the new monitor preference columns to existing databases. Screenshot pixel-diff rendering and an in-app digest scheduler are still not fully implemented in this iteration.
\n\n## Design follow-up\nSee [`DESIGN_NOTES.md`](DESIGN_NOTES.md) for the shared-fetching, noise-learning, politeness and version-comparison design, plus the remaining implementation slices.\n