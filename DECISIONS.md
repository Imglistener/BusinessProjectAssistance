# Decisions

Approved decisions for the MVP. Open questions and conventions are in `docs/open-items.md`.

| Topic | Decision |
| --- | --- |
| Frontend | React + TypeScript. |
| Financial scope | Budgets and expenses only for the MVP. Revenue later. |
| Currency | One currency per project. MAD for now. |
| Auth | Login and signup screens, password-hash authentication. Public access later. |
| AI actions | Advise, draft and calculate (read-only). |
| AI provider | Groq for now; OpenAI or Anthropic later. Monthly cost cap computed by the backend. |
| Metric definitions | Spec Section 7 approved; check for possible errors later. |
| AI defaults (2026-10-30) | Default pricing, app-wide cost cap, minimal data sent to the provider, no server-side conversation history. See `docs/open-items.md`. |
