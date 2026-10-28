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
flask --app wsgi db upgrade   # after the first migration is generated
flask --app wsgi run

# frontend (new terminal)
cd frontend
npm install
npm run dev
```

Run backend tests: `cd backend && pytest`

## Principles

- Financial calculations live in `backend/app/services/metrics.py` (Decimal arithmetic, tested).
- The AI never runs SQL or does arithmetic itself; it calls allowlisted read-only tools.
- Authorization is enforced server-side on every endpoint and AI tool.
