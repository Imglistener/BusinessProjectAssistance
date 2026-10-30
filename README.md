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

## AI assistant

Set `GROQ_API_KEY` in `.env` (server-side only) and restart the backend; without it the
Assistant page says it isn't set up and everything else works normally.

- `POST /api/ai/chat` with `{organization_id, message, project_id?, history?}` returns
  `{answer, tool_trace, ai_generated}`.
- The model can only call the read-only tools in `backend/app/services/ai_tools.py`; each one
  re-checks organization membership and project access. All figures come from `metrics.py`.
- Provider code is in `ai_provider.py` (Groq, OpenAI chat format); add another provider there.
- Limits: monthly USD cap (`AI_MONTHLY_COST_CAP_USD`, priced with `AI_*_PRICE_PER_MTOK_USD`),
  per-user rate limit and a timeout. Each request logs token counts and cost in `ai_usage`;
  question and answer text are not stored on the server.

## Principles

- Financial calculations live in `backend/app/services/metrics.py` (Decimal arithmetic, tested).
- The AI never runs SQL or does arithmetic itself; it calls allowlisted read-only tools.
- Authorization is enforced server-side on every endpoint and AI tool.
