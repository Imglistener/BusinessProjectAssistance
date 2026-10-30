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

## Members and invites (implemented, to confirm)
- No email provider yet: an owner creates an invite and gets a link to send themselves. The link
  works only for the account with that email, expires after 7 days, and only its SHA-256 hash is stored.
- Only owners invite, change roles and remove members (spec: project managers invite "only if granted";
  not granted for now). Anyone can leave. The last owner can't leave, be removed or be demoted.
- System administrator can't be given through the app.
- Removed members keep their row (status "removed") for the audit trail; their tasks stay assigned to them.
- Members' emails are visible to owners only.
- Users can belong to several organizations; the sidebar shows a switcher when they do.

## Email and password reset (implemented)
- Provider: Resend, behind an `EmailSender` interface; `console` mode until a domain is verified.
- Reset: same reply whether or not the email has an account; single-use link, 30 minutes, newest link
  replaces older ones, at most 3 per account per hour; only the token hash is stored.
- Existing login tokens aren't revoked by a reset (JWTs are stateless and expire on their own).
- Invites are also emailed when Resend is on; the copy-link option stays.
- Templates live in the code (`services/email.py`), not in Resend, so they're versioned and tested with the app.

## Search and filters (implemented)
- Projects: text search on name and description (case-insensitive, wildcards treated as text), status,
  over budget, has overdue tasks; sort by newest, name or end date. No pagination yet (fine for small teams).
- Expenses: category, date range and voided; the response includes the valid total for the whole filter.
- Tasks: status (incl. "open"), assignee (incl. "assigned to me", unassigned) and overdue, filtered in the browser.

## Still open
- Report export format, notifications.
- A domain for sending email (needed before switching EMAIL_PROVIDER to resend).
- Hosting and backup plan.
