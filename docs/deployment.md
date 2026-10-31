# Deployment and operations

How to run BusinessProjectAssistance in production, and what to check before going live.
Local development is covered in the README.

## What runs where

| Part | What it is | Notes |
| --- | --- | --- |
| Frontend | Static files from `frontend/dist` (`npm run build`) | Any static host or the reverse proxy. Set `VITE_API_BASE_URL` at build time if the API is on another origin. |
| Backend | Flask app `backend/wsgi.py:app` | Run with a WSGI server, e.g. `gunicorn -w 1 -b 127.0.0.1:5000 wsgi:app` (Linux) or `waitress-serve --port=5000 wsgi:app` (Windows). |
| Database | PostgreSQL 16 | Managed service or the `docker-compose.yml` container. |
| Reverse proxy | nginx, Caddy or the host's load balancer | Terminates HTTPS, serves the frontend, forwards `/api` to the backend. |

**One backend process for now.** Login and signup rate limits are counted in memory per process.
With several workers or servers, each keeps its own counts, so the limits get weaker. Before scaling
out, move the counts to a shared store (Redis, for example) in `backend/app/services/ratelimit.py`.

## Configuration

All settings are environment variables (see `.env.example`). Never commit real values.

| Variable | Production value |
| --- | --- |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Long random values, different from each other: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The backend logs a warning at startup when they are placeholders or short. Changing `JWT_SECRET_KEY` logs everyone out. |
| `DATABASE_URL` | `postgresql+psycopg2://user:password@host:5432/dbname` |
| `CORS_ORIGINS` | The frontend address, e.g. `https://app.example.com`. Not `*`. |
| `PROXY_FIX_X_FOR` | `1` when one reverse proxy sits in front of the backend, so rate limits see the real client IP. `0` if nothing is in front. |
| `JWT_ACCESS_TOKEN_HOURS` | How long a login lasts (default 12). |
| `APP_BASE_URL` | The frontend address, used in emailed links. |
| `EMAIL_PROVIDER`, `RESEND_API_KEY`, `EMAIL_FROM` | `resend`, a sending-only key restricted to the verified domain, and an address on that domain. |
| `UPLOAD_DIR` | A persistent folder for uploaded receipts (outside the code folder, on a backed-up disk). |
| `GROQ_API_KEY`, `AI_*` | AI provider key and limits. The key stays on the server. |

## First deployment

1. Create the database and set `DATABASE_URL`.
2. Install backend dependencies: `pip install -r backend/requirements.txt` plus the WSGI server.
3. Apply migrations: `cd backend && flask --app wsgi db upgrade`. Run this again after every update, before restarting.
4. Build the frontend: `cd frontend && npm ci && npm run build`.
5. Configure the reverse proxy: HTTPS only (redirect HTTP), allow request bodies of at least
   `MAX_UPLOAD_MB` + 1 MB on `/api/` (nginx: `client_max_body_size 11m;`), serve `frontend/dist`, send unknown paths to
   `index.html` (the app uses client-side routes such as `/invite/...`), and forward `/api/` to the backend.
6. Start the backend and check `GET /api/health` returns `{"status": "ok"}`.

## Before going live

- [ ] HTTPS with automatic certificate renewal.
- [ ] Secrets set as above; no warnings about weak secrets in the backend log.
- [ ] `CORS_ORIGINS` set to the real frontend address.
- [ ] `PROXY_FIX_X_FOR` matches the number of proxies.
- [ ] Debug mode off (`flask run` is for development; use the WSGI server).
- [ ] Email domain verified in Resend and a test reset email received.
- [ ] AI monthly cap (`AI_MONTHLY_COST_CAP_USD`) and token prices set.
- [ ] Backups running and one restore tested (below).

## Backups and recovery

Proposed baseline, to be confirmed with the project owner:

| | Proposal |
| --- | --- |
| Frequency | Daily full backup; managed PostgreSQL point-in-time recovery if the host offers it. |
| Retention | 7 daily, 4 weekly, 3 monthly. |
| Location | Off the database server, in another region or provider; encrypted. |
| Restore test | Before launch, then every quarter: restore into a scratch database and check the app starts and shows data. |

Manual backup and restore:

```bash
pg_dump --format=custom --file=bpa-$(date +%F).dump "$DATABASE_URL_PLAIN"
pg_restore --clean --no-owner --dbname="$DATABASE_URL_PLAIN" bpa-2026-10-30.dump
```

`DATABASE_URL_PLAIN` is the same URL without the `+psycopg2` part (`postgresql://...`).

Back up `UPLOAD_DIR` (uploaded receipts) on the same schedule, e.g. with `rsync` or the host's volume
snapshots; a database restore without it leaves receipts listed but unavailable.

What a backup contains: everything, including password hashes, invite and reset token hashes, audit
logs and AI usage rows (no prompt text). Treat backups as confidential.

## Map, place search and routing

The trip map uses OpenStreetMap services directly from the browser: map tiles (tile.openstreetmap.org),
place search (Nominatim) and road distance (the public OSRM demo server). They are free but rate-limited
and meant for light use: the app searches only on Enter and at most once a second. For real traffic,
switch to a hosted provider or self-host Nominatim/OSRM by changing `frontend/src/lib/geo.ts` and the tile URL
in `frontend/src/components/TripRoute.tsx`.

## Fuel price sync

`flask --app wsgi fuel-prices-sync` reads average pump prices from prix-gasoil-maroc.teraedge.ma for every
MAD organization. Run it once a day (cron or the host's scheduler); it reads six pages, one second apart, and
caches for six hours. If the site changes its layout the command fails without touching saved prices.

## Logs

- The backend logs to standard output/error. Keep them for troubleshooting, without request bodies.
- Logged on purpose: AI provider errors (status only), email send failures (no body), weak-secret warnings.
- In `EMAIL_PROVIDER=console` mode the backend logs whole emails, including live reset links.
  Never use console mode in production.
