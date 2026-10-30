# Open items and spec/diagram reconciliation

## Resolved by DECISIONS.md
- Frontend: React/TypeScript (the diagram shows Flutter Web; ignore that).
- MVP financial scope: budgets and expenses only. Revenue later (no Revenue model yet).
- Currency: one per project, default MAD.
- Auth: login/signup screen with password hashing.
- AI: advise, draft, calculate (read-only). Groq first, provider abstraction for later.

## Differences between the diagram and the DOCX spec (to confirm)
- Diagram has Resource / ProjectResource (resource allocation); the DOCX has none. Included as models, not exposed in the API yet.
- Diagram has ProjectMember; the DOCX relies on organization roles plus project owner. Included.
- Diagram stores AIConversation/AIMessage; the DOCX has AISuggestion and says to avoid storing sensitive prompts unnecessarily. Conversation models included, retention policy to decide.
- Diagram Expense has receipt_url; the DOCX lists attachments as "Could / later". Field kept nullable.
- Diagram: "budget divided into categories/allocations". Not in the DOCX; deferred (see BudgetAllocation idea).
- Diagram Project has a `type` field; not in the DOCX. Kept nullable.
- Role names: DOCX has Owner, Project Manager, Contributor, Viewer, System Administrator. Implemented as an enum; permissions to confirm.

## Conventions chosen (Section 7 approved, "check for errors later")
- Budget variance = actual expenses - approved budget (positive means over budget).
- Budget consumed % is None ("N/A") when budget is zero.
- Task completion % counts non-cancelled tasks; None when there are no eligible tasks.
- Overdue: status not done/cancelled and due_date < today in the organization timezone. Paused ("blocked") tasks: still overdue (to confirm).
- Expenses with status other than "valid" are excluded from totals.
- Rounding: ROUND_HALF_UP to 2 decimals.

## AI assistant (approved defaults, 2026-10-30)
- Model: `openai/gpt-oss-120b` on Groq (llama-3.3-70b-versatile is no longer offered on the account).
- Cost cap: per-request cost = tokens x configured price per million tokens
  (defaults 0.15 in / 0.75 out USD; verify against Groq's pricing page). The cap is app-wide, not per organization.
- Conversations are not stored server-side: the browser keeps the conversation and sends the last
  12 turns with each question. `ai_conversations`/`ai_messages` stay unused until a retention policy is chosen.
- Data sent to the provider: project names, figures, task titles and assignee names. No emails, no expense descriptions.
- Added a seventh read-only tool, `list_projects`, so the assistant can find project IDs.
- Rate limit: 10 questions per user per minute (configurable).

## Still open
- Report export format, notifications, email provider for password reset.
- Hosting and backup plan.
