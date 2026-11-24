# Hosting online

How to put the app on the internet for trials: the site on Cloudflare, the backend on Render, the database on Neon.
Checked against the providers' pages on 2026-11-24. For commercial use, see "Going commercial".

```
browser -> Cloudflare Worker (site + /api proxy) -> Render (Flask backend) -> Neon (PostgreSQL)
           https://....workers.dev                  free web service          free plan
```

## Why not only GitHub Pages or only Cloudflare

- **GitHub Pages** serves static files only (no Python), and its rules exclude running an online business or
  commercial software on it.
- **Cloudflare alone:** Python Workers have no working threads and only temporary in-memory files, and psycopg2 (the
  database driver) isn't listed as supported, so the backend would need a rewrite. Cloudflare Containers could run it
  as it is, but need the Workers Paid plan (5 USD a month), and still an outside PostgreSQL.

## Free-plan limits

| Part | Limit |
| --- | --- |
| Cloudflare Worker | 100,000 API requests a day; the site's files don't count. |
| Render | Sleeps after 15 minutes without visits; the next visitor waits about a minute. 750 hours a month. Local files are lost on restart, so receipts go in the database. No email ports 25, 465 or 587. Render says not to use it for production. |
| Neon | 1 GB, 100 compute hours a month, sleeps when idle. Not a trial; no card needed. Receipts count towards the 1 GB. |

## Set it up (about 30 minutes)

1. **Push the code to GitHub** (`git push`). Render deploys from it.
2. **Neon:** create a project (region Frankfurt, PostgreSQL 16) and copy the connection string
   (`postgresql://...?sslmode=require`).
3. **Cloudflare:** in `frontend/`, run `npx wrangler@4 login`, then `npm run deploy:cloudflare`. It prints the
   address, `https://business-project-assistance.<you>.workers.dev`. The site loads; `/api` isn't set up yet.
4. **Render:** New > Blueprint, pick the repository (it reads `render.yaml`) and fill in:
   `DATABASE_URL` (Neon), `APP_BASE_URL` and `CORS_ORIGINS` (both the Cloudflare address, no final `/`),
   `GEMINI_API_KEY`, `GROQ_API_KEY`. Leave the SMTP ones and `EMAIL_FROM` empty for now. Secrets are generated;
   migrations run on start.
5. **Connect them:** copy `PROXY_SECRET` from Render's Environment page, then in `frontend/`:
   `npx wrangler@4 secret put PROXY_SECRET` (paste it) and `npx wrangler@4 secret put BACKEND_URL` (the Render
   address, e.g. `https://bpa-backend.onrender.com`).
6. Open the Cloudflare address and sign up. **Don't load `demo-data`** online: its password is public.

Later: `git push` redeploys the backend; `npm run deploy:cloudflare` redeploys the site.

## Email

`EMAIL_PROVIDER=none` to start with: invitations still give a link to send yourself, but password resets can't be
emailed. Gmail doesn't work on Render's free plan (blocked ports). Use an email service with SMTP on port 2525 (not
tested here): fill in `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` and `EMAIL_FROM`, and set `EMAIL_PROVIDER=smtp`.
With a domain, Resend (`EMAIL_PROVIDER=resend`) works over HTTPS.

## Before sharing the address

- **Anyone can sign up**, and everyone uses your AI keys: the monthly cap (`AI_MONTHLY_COST_CAP_USD`) and the
  per-person limit are the only brakes.
- On Google's free tier, prompts (which include the organization's figures) may be used to improve its products.
- `PROXY_SECRET` makes the backend refuse anything that doesn't come through the Worker. Keep it secret.

## Quick demo from your own computer

No accounts: `docker compose up -d --build`, then `cloudflared tunnel --url http://localhost:8080` gives a temporary
`trycloudflare.com` address. It changes every time, works while the computer is on, and Cloudflare means it for tests.

## Going commercial

Move Render to a paid instance (no sleeping), Neon or another managed PostgreSQL with backups, a paid AI plan, your
own domain with email, and receipts in object storage. Then follow "Before going live" in `deployment.md`.
