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
- Gemini can be used instead (`AI_PROVIDER=gemini`, `GEMINI_API_KEY`; default model `gemini-3.5-flash-lite`,
  thinking effort low). Added 2026-11-01 because Groq's free tier allows only 8K tokens a minute. Not yet run
  against the real Gemini API (no key yet): the adapter follows Google's OpenAI-compatibility docs and sends
  back tool-call thought signatures (`extra_content`) as received. Free-tier prompts may be used by Google to
  improve its products.
- Checked 2026-11-01 with the user's free key: `gemini-3.8-flash` didn't answer at all (even "Say ok" timed out
  after 90 s), `gemini-3.6-flash` answered in seconds but hit its per-minute limit on the second question,
  `gemini-3.5-flash-lite` works and is the default. Flash-Lite drifted into French for English questions, so the
  backend now detects the message's language (Arabic script, or common French/English words) and names it in
  the prompt; unclear messages fall back to the app's language.
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

## Milestones (implemented)
- Owners and project managers create, edit, complete/reopen and delete milestones; everyone in the
  organization can see them. Archived projects are read-only.
- Progress = task completion % of the milestone's linked tasks (same rule as projects: cancelled excluded).
- Overdue = open with a due date before today in the organization timezone (same as tasks).
- Completing a milestone is a manual decision; it doesn't require all linked tasks to be done.
- Deleting a milestone keeps its tasks and unlinks them.
- The AI project summary includes milestones.

## Project report and exports (implemented, default format)
- Report page per project (budget, spending by category and month with shares, tasks, overdue,
  next 14 days, milestones, definitions). PDF via the browser's "Save as PDF" print option.
- CSV exports of expenses (all statuses, with a status column) and tasks. UTF-8 with BOM for Excel;
  cells that would run as formulas (=, +, -, @) are prefixed with an apostrophe.
- Any member who can see the project can view and export it. Exports aren't audited (they change nothing).
- Excel (.xlsx) export and a server-generated PDF are possible later if needed.

## Security pass (implemented)
- Rate limits: 5 failed logins per email per 15 min (locks even the right password until the window
  passes), 30 login attempts per IP per 15 min, 10 signups / 10 reset requests / 20 reset confirmations
  per IP per hour. In memory, per process (see docs/deployment.md).
- Logins last 12 hours (was the library default of 15 minutes); the app returns to the login page when one expires.
- CORS origins and proxy settings are configurable; weak or placeholder secrets log a warning at startup.

## Project activity (implemented)
- Project page "Activity" list from the audit log, newest first, 10 at a time; visible to anyone who can see the project.
- Audit entries now carry `project_id` (backfilled by migration) so the list is a simple indexed query.
- Organization-level events (members, invites) aren't shown per project; an organization activity view could come later.

## AI evaluation (implemented)
- `flask --app wsgi ai-eval`: 8 known-answer questions on the demo data, checked against backend figures.
  Last run 2026-10-30 with openai/gpt-oss-120b on Groq: 8/8 passed.
- Groq's per-minute token limit is low on this account: a few questions in a row can hit HTTP 429. The backend
  waits once for short Retry-After values, otherwise tells the user the assistant is busy. A paid Groq tier
  (or smaller prompts) would raise the limit.

## Inventory (implemented, my defaults)
- Organization-level stock items (name, SKU, unit, unit cost in the default currency, reorder level, location).
- Quantities change only through movements: receive, issue (optionally to a project), adjust (signed, reason
  required) and stock counts (set to the counted quantity; differences recorded). Stock can't go below zero.
- Roles: owners/project managers manage items and adjust; contributors receive, issue and count; viewers read.
- Stock value = quantity x current unit cost (no FIFO/average costing). Items without a cost are left out of the value.
- Stock issued to a project is listed under "Materials used" but not added to project spending (no double counting
  with purchase expenses). The AI has a read-only `get_inventory_status` tool.
- Replaced the unused `resources`/`project_resources` tables (the migration refuses if they contain rows).

## Trip planning (implemented, my defaults)
- Trips belong to a project: destination, dates, purpose, status (planned/booked/completed/cancelled),
  optional budget, travelers (organization members; the creator by default).
- Itinerary items: flight/train/car/hotel/meeting/other, date within the trip, optional local "HH:MM" times,
  location, booking reference, estimated cost. Trip dates can't change so that items fall outside them.
- Spend = valid expenses linked to the trip (part of the project's spending, not extra). Estimate = sum of item costs.
- Contributors and up plan trips; managers or the trip's creator edit/delete. Deleting unlinks its expenses.
- Upcoming planned/booked trips appear in the dashboard "Coming up" list and in the AI project summary.

## User guide
- `docs/user-guide.md`, written for end users (owners, managers, contributors). Update it when features change.

## Expense receipts (implemented, my defaults)
- PDF/JPEG/PNG/WebP, type checked from the file contents; 10 MB and 10 files per expense; random stored names.
- Stored in a local folder (`UPLOAD_DIR`). For multiple servers or managed hosting, move to object storage
  (S3-compatible) by implementing save/read/delete in `services/storage.py`.
- Always served as downloads with `nosniff`, through permission-checked endpoints. No virus scanning yet.

## In-app notifications (implemented, my defaults)
- Stored per user; created for: task assigned, added as trip traveler, project crosses over budget (project owner
  + organization owners), item crosses into low stock (owners + project managers), invite accepted (inviter).
- Never for your own actions; only to active members; hidden after leaving the organization.
- Sidebar count refreshes every minute while the tab is visible. Email copies of notifications can be added
  once email is configured (needs the email domain).

## Trip routes, fuel estimates, calculations (implemented, my defaults)
- Map picker: Leaflet with OpenStreetMap tiles, Nominatim search (on Enter) and OSRM road distance (public demo
  server; fine for now, not for heavy production use). Built-in Moroccan cities resolve instantly; without a
  route the server uses straight-line distance x 1.3. Google Maps was replaced at the user's request.
- Fuel prices: "Update from website" / `flask fuel-prices-sync` read averages from prix-gasoil-maroc.teraedge.ma
  (national + Casablanca, Rabat, Marrakech, Tangier, Agadir; robots.txt allows it, ai-train=no, use=reference;
  source credited). Currently the site shows the same average for every city. Manual prices still possible. Flagged when older than 30 days. Demo prices are examples, not real current prices.
- Vehicle consumption: built-in typical ranges for 10 vehicle classes (L/100 km). Estimate range: lowest
  consumption x planned distance x price -3%, up to highest consumption x (distance + variance) x price +3%.
- AI tools: calculate (safe Decimal evaluator), vat (default 20%), budget_what_if, estimate_trip_fuel_cost,
  estimate_fuel_cost. The assistant is told to use tools for every calculation.

## Assistant drafts projects (implemented)
- propose_project returns a draft (validated); the user edits it and clicks "Create project". The server
  validates again and creates project, milestones and tasks in one transaction; only owners/project managers.
- Audited as project.created with source "assistant_plan".

## Public landing page (implemented)
- "/" shows the product page to visitors (signed-in users get "Open your dashboard"). Replaces the splash screen.

## Email delivery (implemented)
- For now: Gmail over SMTP (EMAIL_PROVIDER=gmail, App Password) for password resets and invites. Verified with a
  real test email on 2026-10-31. A generic SMTP option exists for other providers.
- Later, with a domain: switch EMAIL_PROVIDER to resend (sender already built).

## Project inventories and warehouses (implemented, your choices + my defaults)
- Each project has its own inventory; the organization's earlier shared stock became "General stock" (items and
  warehouses with no project). Stock moves between them with "Move to another inventory" (found by name, else
  created; a different unit is refused).
- Warehouses have an address and a map position (OpenStreetMap search / click). An item's stock can be split
  across warehouses (inventory_stock); transfers move it between them. Stock counts are per warehouse.
- Items can be deleted for good (with their history; the audit log keeps a record). Warehouses only when empty.
- Roles: contributors receive, issue, transfer and count; owners and project managers add/edit/delete items,
  adjust, move between inventories and manage warehouses.
- New projects can start with an inventory (optional second step, or in an assistant draft).
- Assistant: find_inventory_items and list_warehouses read any inventory; propose_stock_changes drafts receive /
  issue / adjust / create / transfer / move / delete lines. It can't create warehouses (they need a map position);
  "organize" means proposing transfers.
- Checked on Postgres 2026-11-02 (Docker): the migration adds enum values with ALTER TYPE; upgrade, downgrade and `db check` pass.

## Test pass 2026-11-01
- Backend 344 tests, frontend type-check and build, smoke test (15 steps), `ai-eval` on Gemini Flash-Lite 11/11,
  and screenshots in English, French and Arabic, light and dark, desktop and phone width.
- Dependencies: `npm audit` flagged React Router 6 (open redirect, fixed only in 7.18+) and Vite 5 (dev-server
  issues, several Windows-specific). Upgraded to React Router 7.18.5, Vite 7.3.7 and @vitejs/plugin-react 5.2;
  `npm audit` now reports 0. `pip-audit` on the backend: no known vulnerabilities.
- Fixed: Radix components (tabs, menus, selects) were left to right in Arabic; the inventory tabs showed items
  and warehouse cards in LTR order. A direction provider now follows the app language.
- Fixed: a long option label in a select pushed the next field over in two-column dialogs (Move to another
  inventory).
- Fixed in the assistant: Flash-Lite answered English questions in French (now the backend names the reply
  language); it sometimes left out the warehouse of a new item or guessed one that doesn't exist (tool
  descriptions now say so, and the model is told to correct guessed names itself). Model answers still vary:
  check the draft card before confirming.
- Postgres migration checked 2026-11-02 in Docker: every migration applies on PostgreSQL 16, the inventory
  migration downgrades and upgrades again, and `flask db check` finds no difference.

## Deleting projects (implemented, my defaults)
- Owners only. One project (project page) or several (Select on the dashboard), all or nothing. The confirmation
  shows exact counts from POST /organizations/:id/projects/delete-preview and asks to type "delete".
- Removed: the project, expenses and receipt files, tasks, milestones, trips, assistant conversations and links in
  notifications. Kept: stock movements (detached, noted "Issued to deleted project X") and the audit log, plus a
  "project.deleted" entry with who deleted what. Archiving remains the everyday option.

## Assistant drafts stock changes (implemented)
- propose_stock_changes drafts receive / issue / adjust / new-item lines from plain language and previews the
  quantity before and after; find_inventory_items looks up any item. Nothing is saved until the user confirms.
- POST /organizations/:id/inventory/changes re-checks every line and saves them all or none, through the same
  code as the Stock page (roles, low-stock alerts, history). A delivery of an untracked item becomes a new item.

## Languages (implemented, my defaults)
- English, French and Arabic (Modern Standard Arabic, right-to-left layout, Moroccan month names). The picker (sidebar, landing page, login pages) saves the choice in the
  browser and on the account; emails (password reset, invites) use the account's language, invites the
  inviter's. Notifications, error messages and fuel-estimate notes are shown in the reader's language.
- Translations are mine: worth a review by a native speaker before launch, especially the landing page.
- Names you enter (projects, tasks, categories, items) are shown as typed; they aren't translated.
- Numbers: 1 850,50 MAD in French (fr-FR grouping), 1,850.50 MAD in English, 1.850,50 MAD in Arabic (ar-MA,
  Latin digits).
- Arabic activity lines and notifications use verbal nouns ("Salma: إنشاء المشروع") because the app doesn't know
  people's gender, which Arabic verbs would need.

## Still open
- A domain for sending email (needed before switching EMAIL_PROVIDER to resend).
- Hosting choice; confirm the backup proposal in docs/deployment.md.
