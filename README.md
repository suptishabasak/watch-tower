# Watchtower — Website Change Detector

**Live website:** https://watch-tower-yann.onrender.com/

Watchtower monitors public web pages and records meaningful content changes while filtering common page noise. The existing React dashboard is served alongside the FastAPI backend.

## Live Demo

Visit **[Watchtower](https://watch-tower-yann.onrender.com/)** to open the deployed application.

- **Dashboard:** https://watch-tower-yann.onrender.com/
- **API health check:** https://watch-tower-yann.onrender.com/api/health
- **API documentation:** https://watch-tower-yann.onrender.com/docs

The deployed application may take a little time to respond if the hosting service has been idle. Availability and data persistence depend on the hosting configuration.

## Requirements for Local Development

- Python 3.11+ recommended
- Node.js 18+
- Playwright Chromium browser

## Run the Backend (Windows PowerShell)

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

## Run the Frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (usually http://localhost:5173).

## Configuration

Edit `backend/.env` locally. Do not commit it. Start with `.env.example`.

Useful settings include `DEMO_MODE`, `SCHEDULER_ENABLED`, `DISCORD_WEBHOOK_URL`, `MAX_CONCURRENT_CHECKS`, and `PAGE_TIMEOUT_SECONDS`.

Configure a Discord webhook only if you want notifications. Webhook URLs and other credentials are secrets and must never be shared or committed.

## Features

- Monitor creation, editing, pause/resume, and manual checks
- Scheduled checks with bounded worker concurrency
- Playwright page rendering, screenshots, and normalized text snapshots
- Content hashing to prevent duplicate versions when content is unchanged
- Text diff/history and sensitivity/focus filtering
- Visual CSS-region picker with watch/ignore selection
- Notification deduplication and Discord alerts
- Public URL validation, failure status, and retry-safe notification delivery
- Demo data for exploring the dashboard

## Visual Region Picker

In Add Monitor or Edit, enter a public URL and choose **Choose regions visually**.

Click elements in the static preview to save CSS selectors under **Watch** (green) or **Ignore** (orange). Click Done and save the monitor.

Watched selectors limit the text compared on each check; ignored selectors are removed before extraction. Selectors are saved with the monitor and returned by the API.

Since the preview is static and scripts/forms are disabled, highly dynamic pages may look different from the live site.

## Important Limitations

- This is a prototype, not a hardened production monitoring service.
- Do not expose it publicly without appropriate authentication, deployment hardening, and a persistent production database.
- Screenshot snapshots are saved and shown in history when storage is available. A pixel-highlighted screenshot-diff overlay remains a frontend follow-up; use saved before/after images and text diff/history.
- Discord, SMTP email, and Telegram notifications require valid server-side credentials.
- The `/api/digest?hours=24` endpoint returns a digest payload. A built-in timed digest sender is not yet enabled.
- Public-only URL checks reduce SSRF risk but should be combined with network-level egress restrictions in production.

**Hosting note:** If the deployed service uses an ephemeral filesystem, SQLite data and screenshots may be lost when the container restarts or is replaced. Persistent storage must be configured separately if you need those files to survive redeployments.

## Deployment (Render)

The app is configured for a single Docker-based Render web service serving both the React dashboard and FastAPI/Playwright backend. This keeps `/api` and `/screenshots` on the same
