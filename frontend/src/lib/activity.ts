import { getLocale, t } from "../i18n";
import {
  PRIORITY_LABEL,
  STATUS_LABEL,
  TASK_STATUS_LABEL,
  TRIP_STATUS_LABEL,
  formatDate,
  formatMoney,
  formatNumber,
} from "./format";

export interface ActivityEntry {
  id: number;
  action: string;
  entity_type: string;
  entity_id: number | null;
  /** Current name of the record (task title, expense summary); null once deleted. */
  label: string | null;
  actor: string | null;
  at: string;
  meta: Record<string, unknown>;
}

type Change = [unknown, unknown];
const isChange = (v: unknown): v is Change => Array.isArray(v) && v.length === 2;

const quote = (s: string | null, fallback: string) => (s ? t("“{text}”", { text: s }) : fallback);
const date = (v: unknown) => (typeof v === "string" ? formatDate(v) : t("no date"));
/** Field names as they appear in sentences. */
const FIELD: Record<string, string> = {
  name: t("name"),
  description: t("description"),
  currency: t("currency"),
  title: t("title"),
  amount: t("amount"),
  expense_date: t("date"),
  category: t("category"),
  trip_id: t("trip"),
};
const field = (f: string) => FIELD[f] ?? f.replace("_", " ");

/** One plain sentence (without the actor) describing an audit entry. */
export function describe(e: ActivityEntry, people: Record<string, string>, currency: string): string {
  const m = e.meta;
  const person = (v: unknown) => (typeof v === "number" ? (people[String(v)] ?? t("a former member")) : t("nobody"));
  const money = (v: unknown) => (typeof v === "string" ? formatMoney(v, currency) : String(v));

  switch (e.action) {
    case "project.created":
      return t("created the project");
    case "project.archived":
      return t("archived the project");
    case "project.updated":
      return joinParts(
        Object.entries(m).map(([f, change]) => {
          if (!isChange(change)) {
            if (f === "name") return t("renamed the project");
            if (f === "description") return t("edited the description");
            return t("changed the {field}", { field: field(f) });
          }
          const [a, b] = change;
          if (f === "status" && a === "archived") return t("restored the project");
          if (f === "status")
            return t("changed the status from {from} to {to}", {
              from: STATUS_LABEL[String(a)],
              to: STATUS_LABEL[String(b)],
            });
          if (f === "budget") return t("changed the budget from {from} to {to}", { from: money(a), to: money(b) });
          if (f === "start_date") return t("changed the start date from {from} to {to}", { from: date(a), to: date(b) });
          if (f === "end_date") return t("changed the end date from {from} to {to}", { from: date(a), to: date(b) });
          return t("changed the {field} from {from} to {to}", {
            field: field(f),
            from: String(a ?? t("none")),
            to: String(b ?? t("none")),
          });
        }),
      );
    case "expense.created": {
      const amount = typeof m.amount === "string" ? formatMoney(m.amount, String(m.currency ?? currency)) : "";
      return t("recorded an expense: {details}", { details: [m.category, amount].filter(Boolean).join(", ") });
    }
    case "expense.voided":
      return t("voided the expense {label}", { label: e.label ?? "" }).trim();
    case "expense.updated":
      return t("edited the expense {label}", { label: e.label ?? "" }).trim() + changesSuffix(m, { amount: money, expense_date: date });
    case "task.created":
      return t("added the task {task}", { task: quote(e.label, t("(since deleted)")) });
    case "task.updated": {
      const task = quote(e.label, t("a task"));
      return joinParts(
        Object.entries(m).map(([f, change]) => {
          if (!isChange(change))
            return f === "title"
              ? t("renamed a task to {task}", { task })
              : t("edited the {field} of {task}", { field: field(f), task });
          const [a, b] = change;
          if (f === "status")
            return t("moved {task} from {from} to {to}", {
              task,
              from: TASK_STATUS_LABEL[String(a)],
              to: TASK_STATUS_LABEL[String(b)],
            });
          if (f === "assignee_id")
            return b === null
              ? t("unassigned {task}", { task })
              : t("assigned {task} to {person}", { task, person: person(b) });
          if (f === "priority")
            return t("changed the priority of {task} from {from} to {to}", {
              task,
              from: PRIORITY_LABEL[String(a)],
              to: PRIORITY_LABEL[String(b)],
            });
          if (f === "due_date")
            return t("changed the due date of {task} from {from} to {to}", { task, from: date(a), to: date(b) });
          if (f === "milestone_id") return t("changed the milestone of {task}", { task });
          return t("edited the {field} of {task}", { field: field(f), task });
        }),
      );
    }
    case "milestone.created":
      return t("added the milestone {milestone}", { milestone: quote(e.label, t("(since deleted)")) });
    case "milestone.deleted": {
      const n = typeof m.unlinked_tasks === "number" ? m.unlinked_tasks : 0;
      return n
        ? t("deleted a milestone ({count} tasks kept, without a milestone)", { count: n })
        : t("deleted a milestone");
    }
    case "milestone.updated": {
      const ms = quote(e.label, t("a milestone"));
      return joinParts(
        Object.entries(m).map(([f, change]) => {
          if (f === "status" && isChange(change))
            return change[1] === "done"
              ? t("completed {milestone}", { milestone: ms })
              : t("reopened {milestone}", { milestone: ms });
          if (f === "due_date" && isChange(change))
            return t("changed the due date of {milestone} from {from} to {to}", {
              milestone: ms,
              from: date(change[0]),
              to: date(change[1]),
            });
          if (f === "title") return t("renamed a milestone to {milestone}", { milestone: ms });
          return t("edited {milestone}", { milestone: ms });
        }),
      );
    }
    case "attachment.added":
      return t("attached {file} to an expense", {
        file: quote(typeof m.filename === "string" ? m.filename : null, t("a file")),
      });
    case "attachment.removed":
      return t("removed {file} from an expense", {
        file: quote(typeof m.filename === "string" ? m.filename : null, t("a file")),
      });
    case "trip.created":
      return typeof m.destination === "string"
        ? t("planned a trip to {destination}", { destination: m.destination })
        : t("planned a trip");
    case "trip.deleted":
      return t("deleted the trip {trip}", { trip: quote(typeof m.title === "string" ? m.title : null, "") }).trim();
    case "trip.item_added":
      return t("added {item} to a trip itinerary", {
        item: quote(typeof m.item === "string" ? m.item : null, t("an item")),
      });
    case "trip.item_removed":
      return t("removed {item} from a trip itinerary", {
        item: quote(typeof m.item === "string" ? m.item : null, t("an item")),
      });
    case "trip.updated": {
      const status = m.status;
      if (isChange(status) && Object.keys(m).length === 1)
        return t("marked a trip as {status}", { status: TRIP_STATUS_LABEL[String(status[1])]?.toLowerCase() ?? "" });
      return t("updated a trip");
    }
    case "inventory.receive":
    case "inventory.issue":
    case "inventory.adjust":
    case "inventory.count": {
      const delta = typeof m.delta === "string" ? Number(m.delta) : 0;
      const amount = `${formatNumber(Math.abs(delta))} ${String(m.unit ?? "")}`.trim();
      const change = `${delta >= 0 ? "+" : "-"}${amount}`;
      const item = String(m.item ?? t("an item"));
      if (e.action === "inventory.count") return t("counted {item}: {change} against the records", { item, change });
      if (e.action === "inventory.adjust") return t("adjusted {item} by {change}", { item, change });
      if (e.action === "inventory.issue") return t("issued {amount} of {item}", { amount, item });
      return t("received {amount} of {item}", { amount, item });
    }
    default:
      return e.action.replace(".", " ").replace("_", " ");
  }
}

function joinParts(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? t("made a change");
  return t("{list} and {last}", { list: parts.slice(0, -1).join(t(", ")), last: parts[parts.length - 1] });
}

/** ": amount 10.00 MAD → 12.00 MAD, date …" for value changes; field names only for text edits. */
function changesSuffix(m: Record<string, unknown>, format: Record<string, (v: unknown) => string>): string {
  const parts = Object.entries(m).map(([f, change]) => {
    const name = f === "description" ? t("note") : field(f);
    if (!isChange(change)) return name;
    const fmt = format[f] ?? ((v: unknown) => String(v ?? t("none")));
    return `${name} ${fmt(change[0])} → ${fmt(change[1])}`;
  });
  return parts.length ? ` (${parts.join(", ")})` : "";
}

const timeFmt = new Intl.DateTimeFormat(getLocale(), {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export const formatWhen = (iso: string) => timeFmt.format(new Date(iso));
