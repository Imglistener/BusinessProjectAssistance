# User guide

BusinessProjectAssistance keeps your projects, budgets, spending, tasks, trips and stock in one place,
and has an assistant that answers questions about them. This guide explains how to use it.

## Getting started

1. **Create an account** with your name, email and a password (at least 8 characters).
2. **Name your organization.** Everything lives inside an organization: projects, people, stock. You become
   its owner. Amounts are in Moroccan dirham (MAD) unless you choose another currency for a project.
3. **Invite your team** from **Members** (see below), then **create your first project** from the dashboard.

Joined through an invite? Open the link you were sent, create an account with the same email address the
invite was sent to, and select **Join**.

Forgot your password? On the login page select **Forgot your password?** and follow the link you receive.

## Who can do what

| | Owner | Project manager | Contributor | Viewer |
| --- | :-: | :-: | :-: | :-: |
| See projects, reports, activity, stock | ✓ | ✓ | ✓ | ✓ |
| Ask the assistant | ✓ | ✓ | ✓ | ✓ |
| Add tasks and expenses | ✓ | ✓ | ✓ | |
| Change own expenses, status of own tasks | ✓ | ✓ | ✓ | |
| Plan trips (and change their own) | ✓ | ✓ | ✓ | |
| Receive, issue and count stock | ✓ | ✓ | ✓ | |
| Create, edit, archive projects; manage milestones | ✓ | ✓ | | |
| Edit any task, expense or trip | ✓ | ✓ | | |
| Manage stock items, adjust stock | ✓ | ✓ | | |
| Invite people, change roles, remove members | ✓ | | | |

## The dashboard

The dashboard shows, for your organization:

- **Totals**: budget, spent and remaining across active projects.
- **Warnings**: how many projects are over budget and how many tasks are overdue.
- **Coming up**: overdue tasks and milestones, and anything due (or any trip leaving) in the next 14 days.
- **My tasks**: open tasks assigned to you.
- **Projects**: search by name or description, filter by status or "only over budget", and sort.

If you belong to more than one organization, switch between them at the top of the left-hand menu.

## Projects

Open a project from the dashboard. A project has a budget, dates and a status (planned, active, on hold,
completed). Owners and project managers can **Edit project** or **Archive** it. Archived projects are
read-only and hidden from the dashboard; open one through the status filter and select **Restore project**.

### Budget and expenses

- **Add expense**: category, amount, date, an optional note and, if relevant, the trip it was for.
- **Spent** is the sum of valid expenses. **Remaining** is budget minus spent; it goes negative (red) when
  you're over budget.
- Expenses are never deleted. If one was a mistake, **Void** it: it stays on record but stops counting.
- Filter expenses by category and dates; the total for the filter is shown under the filters.

### Tasks and milestones

- **Add task** with a priority, due date, assignee and, optionally, a milestone.
- A task is **overdue** when it isn't done or cancelled and its due date has passed.
- **Milestones** are key dates. Link tasks to them to see progress ("3 of 5 tasks done"). Select
  **Mark done** when the milestone is reached.
- Filter tasks by status, assignee ("Assigned to me"), milestone or overdue.

### Trips

Plan business travel under the project it's for.

1. Select **Plan a trip**: title, destination, dates and an optional budget.
2. Open the trip and **Add to itinerary**: flights, trains, hotels, meetings, with times (local to where they
   happen), booking references and estimated costs.
3. Choose who's going under **Travelers**.
4. When you pay for something, record it as an expense on the project and choose the trip. The trip page then
   compares its **budget**, the **itinerary estimate** and what was actually **spent**.

**Print itinerary** gives a clean copy for the travelers.

### Activity

At the bottom of each project, **Activity** lists every change: who did what, and when.

### Report and exports

Select **Report** on a project for a one-page summary: budget, spending by category and month, tasks,
milestones and how each figure is calculated. Use **Print / Save as PDF** to share it, or download the
expenses or tasks as **CSV** files for Excel.

## Inventory

**Inventory** in the left-hand menu tracks what your organization keeps in stock.

- **Add item**: name, unit (pcs, box, kg…), unit cost, a reorder level and where it's kept. Items at or below
  their reorder level are marked **Low stock**.
- **Receive** when stock arrives; **Issue** when it's used, optionally for a project (it then appears under
  **Materials used** on that project). **Adjust** corrects stock for damage or loss, with a reason.
- **Stock count**: count what's on the shelves and enter the numbers. Quantities are set to what you counted
  and the differences are shown and recorded. You can hide the expected quantities while counting.
- **History** shows every change to an item.

Stock issued to a project isn't added to the project's spending; record purchases as expenses if they
should count against a budget.

## The assistant

Select **Assistant** (or **Ask the assistant** on a project) and ask in plain language, for example:

- "Which projects need attention right now?"
- "What are we spending the most on in the office move?"
- "At the current spend rate, how long will the budget last?"
- "What's running low in stock?"
- "Draft a short status update I can share."

The assistant only **reads** your data: it can't change anything. Its figures come from the same
calculations as the rest of the app, and it says when data is missing. Answers are marked "AI-generated":
check important figures on the project page. Your question and the figures needed to answer it are sent to
an external AI provider.

## Members

Owners manage people under **Members**:

- **Invite someone** with their email and a role. You get a link to send them; it works only for that
  email address and expires after 7 days.
- Change a member's role from the list, or **Remove** them. Every organization keeps at least one owner.
- Anyone can **Leave** an organization.

## Good to know

- Your login lasts 12 hours. After that, you're asked to log in again and taken back to where you were.
- After several wrong passwords, logging in is paused for a few minutes.
- Amounts are always shown with their currency. One project uses one currency.
