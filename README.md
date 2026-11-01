# BusinessProjectAssistance

A business project assistant that helps users track budgets, expenses and tasks for their projects, with a read-only AI assistant that explains data and proposes evidence-based actions.

## Stack (see DECISIONS.md)

- Frontend: React + TypeScript (Vite)
- Backend: Python + Flask REST API, SQLAlchemy, Alembic/Flask-Migrate
- Database: PostgreSQL
- AI: Groq for now (provider abstraction for OpenAI/Anthropic later), with a monthly cost cap

## Layout

```
backend/    Flask API, models, metrics service, AI tools, tests
frontend/   React/TypeScript app
docs/       Specification notes and open items
DECISIONS.md  Approved decisions
```

## Quick start

```bash
cp .env.example .env
docker compose up -d db

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# first time only: create the migrations folder and the initial migration
# (the app reads DATABASE_URL from your environment; export it or load .env first)
flask --app wsgi db init
flask --app wsgi db migrate -m "initial schema"
flask --app wsgi db upgrade     # apply migrations (also run after each later migrate)

flask --app wsgi run

# frontend (new terminal)
cd frontend
npm install
npm run dev
```

Run backend tests: `cd backend && pytest`

End-to-end smoke test (drives the running app in a headless browser; it changes data, so use a
scratch database loaded with `demo-data`):

```bash
cd frontend
npx playwright install chromium-headless-shell   # first time only
npm run e2e                                      # or E2E_BASE_URL=http://host:port npm run e2e
```

## Demo data

To see the app with realistic data, run once (after `db upgrade`):

```bash
cd backend
flask --app wsgi demo-data
```

It creates the organization "Atlas Studio" with five projects (one over budget, one behind schedule, one
on track, one planned, one archived), tasks, expenses and milestones dated around today. Log in as
`demo@example.com` / `demo-password` (owner) or `salma.demo@example.com` / `demo-password` (contributor).
On a non-SQLite database it asks for `--yes` first.

## AI assistant

Set `GROQ_API_KEY` in `.env` (server-side only) and restart the backend; without it the
Assistant page says it isn't set up and everything else works normally.

To use Google Gemini instead, create a key at https://aistudio.google.com/apikey, then in `.env` set
`AI_PROVIDER=gemini` and `GEMINI_API_KEY=...` and restart the backend. `AI_MODEL` left empty means
`gemini-3.5-flash-lite`; `gemini-3.6-flash` answers better but allows fewer requests a minute. Your free-tier
limits are shown at https://aistudio.google.com/rate-limit. On Google's free tier, prompts (which include
your organization's figures) may be used to improve Google's products; a paid tier avoids that.

- `POST /api/ai/chat` with `{organization_id, message, project_id?, history?}` returns
  `{answer, tool_trace, ai_generated}`.
- The model can only call the read-only tools in `backend/app/services/ai_tools.py`; each one
  re-checks organization membership and project access. All figures come from `metrics.py`.
- Provider code is in `ai_provider.py` (Groq and Gemini, both through the OpenAI chat format); add
  another provider there.
- Limits: monthly USD cap (`AI_MONTHLY_COST_CAP_USD`, priced with `AI_*_PRICE_PER_MTOK_USD`),
  per-user rate limit and a timeout. Each request logs token counts and cost in `ai_usage`;
  question and answer text are not stored on the server.

Check the assistant against known answers (needs `demo-data` and an AI key; about 3 minutes, a few
thousand tokens per question, counted against the monthly cap):

```bash
flask --app wsgi ai-eval            # all 8 questions
flask --app wsgi ai-eval --only draft
```

It asks fixed questions about the demo organization and checks the answers against figures the backend
computes: budget variance, top spending category, overdue tasks, spend-rate estimate with assumptions,
saying revenue isn't tracked instead of inventing it, refusing a delete request, labelling drafts, and
ignoring instructions planted in the question.

## Email (password reset, invites)

By default `EMAIL_PROVIDER=console`: emails are not sent, they're printed in the backend log, so
reset and invite links can be tested locally. To send real email through Resend:

1. Add a sending subdomain (e.g. `mail.yourdomain.com`) in the Resend dashboard and add the DNS
   records it shows (SPF, DKIM; DMARC recommended) at your DNS provider, then verify the domain.
2. Create an API key with **sending access only**, restricted to that domain.
3. In `.env`: `EMAIL_PROVIDER=resend`, `RESEND_API_KEY=...`, `EMAIL_FROM=BusinessProjectAssistance <no-reply@mail.yourdomain.com>`,
   and `APP_BASE_URL` set to the deployed frontend address. Restart the backend.

Sending uses idempotency keys and one retry; failures are logged without the email body.

## Principles

- Financial calculations live in `backend/app/services/metrics.py` (Decimal arithmetic, tested).
- The AI never runs SQL or does arithmetic itself; it calls allowlisted read-only tools.
- Authorization is enforced server-side on every endpoint and AI tool.
