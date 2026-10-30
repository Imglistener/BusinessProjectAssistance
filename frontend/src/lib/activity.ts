import { PRIORITY_LABEL, STATUS_LABEL, TASK_STATUS_LABEL, TRIP_STATUS_LABEL, formatDate, formatMoney } from "./format";

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

const quote = (s: string | null, fallback: string) => (s ? `“${s}”` : fallback);
const date = (v: unknown) => (typeof v === "string" ? formatDate(v) : "no date");

/** One plain sentence (without the actor) describing an audit entry. */
export function describe(e: ActivityEntry, people: Record<string, string>, currency: string): string {
  const m = e.meta;
  const person = (v: unknown) => (typeof v === "number" ? (people[String(v)] ?? "a former member") : "nobody");
  const money = (v: unknown) => (typeof v === "string" ? formatMoney(v, currency) : String(v));

  switch (e.action) {
    case "project.created":
      return "created the project";
    case "project.archived":
      return "archived the project";
    case "project.updated":
      return joinParts(
        Object.entries(m).map(([field, change]) => {
          if (!isChange(change)) {
            if (field === "name") return "renamed the project";
            if (field === "description") return "edited the description";
            return `changed the ${field.replace("_", " ")}`;
          }
          const [a, b] = change;
          if (field === "status" && a === "archived") return "restored the project";
          if (field === "status")
            return `changed the status from ${STATUS_LABEL[String(a)]} to ${STATUS_LABEL[String(b)]}`;
          if (field === "budget") return `changed the budget from ${money(a)} to ${money(b)}`;
          if (field === "start_date" || field === "end_date")
            return `changed the ${field === "start_date" ? "start" : "end"} date from ${date(a)} to ${date(b)}`;
          return `changed the ${field.replace("_", " ")} from ${String(a ?? "none")} to ${String(b ?? "none")}`;
        }),
      );
    case "expense.created": {
      const amount = typeof m.amount === "string" ? formatMoney(m.amount, String(m.currency ?? currency)) : "";
      return `recorded an expense: ${[m.category, amount].filter(Boolean).join(", ")}`;
    }
    case "expense.voided":
      return `voided the expense ${e.label ?? ""}`.trim();
    case "expense.updated":
      return `edited the expense ${e.label ?? ""}`.trim() + changesSuffix(m, { amount: money, expense_date: date });
    case "task.created":
      return `added the task ${quote(e.label, "(since deleted)")}`;
    case "task.updated": {
      const task = quote(e.label, "a task");
      return joinParts(
        Object.entries(m).map(([field, change]) => {
          if (!isChange(change))
            return field === "title" ? `renamed a task to ${task}` : `edited the ${field} of ${task}`;
          const [a, b] = change;
          if (field === "status")
            return `moved ${task} from ${TASK_STATUS_LABEL[String(a)]} to ${TASK_STATUS_LABEL[String(b)]}`;
          if (field === "assignee_id") return b === null ? `unassigned ${task}` : `assigned ${task} to ${person(b)}`;
          if (field === "priority")
            return `changed the priority of ${task} from ${PRIORITY_LABEL[String(a)]} to ${PRIORITY_LABEL[String(b)]}`;
          if (field === "due_date") return `changed the due date of ${task} from ${date(a)} to ${date(b)}`;
          if (field === "milestone_id") return `changed the milestone of ${task}`;
          return `changed ${field} of ${task}`;
        }),
      );
    }
    case "milestone.created":
      return `added the milestone ${quote(e.label, "(since deleted)")}`;
    case "milestone.deleted": {
      const n = typeof m.unlinked_tasks === "number" ? m.unlinked_tasks : 0;
      return `deleted a milestone${n ? ` (${n} ${n === 1 ? "task" : "tasks"} kept, without a milestone)` : ""}`;
    }
    case "milestone.updated": {
      const ms = quote(e.label, "a milestone");
      return joinParts(
        Object.entries(m).map(([field, change]) => {
          if (field === "status" && isChange(change))
            return change[1] === "done" ? `completed ${ms}` : `reopened ${ms}`;
          if (field === "due_date" && isChange(change))
            return `changed the due date of ${ms} from ${date(change[0])} to ${date(change[1])}`;
          if (field === "title") return `renamed a milestone to ${ms}`;
          return `edited ${ms}`;
        }),
      );
    }
    case "trip.created":
      return `planned a trip${typeof m.destination === "string" ? ` to ${m.destination}` : ""}`;
    case "trip.deleted":
      return `deleted the trip ${quote(typeof m.title === "string" ? m.title : null, "")}`.trim();
    case "trip.item_added":
      return `added ${quote(typeof m.item === "string" ? m.item : null, "an item")} to a trip itinerary`;
    case "trip.item_removed":
      return `removed ${quote(typeof m.item === "string" ? m.item : null, "an item")} from a trip itinerary`;
    case "trip.updated": {
      const status = m.status;
      if (isChange(status) && Object.keys(m).length === 1)
        return `marked a trip as ${TRIP_STATUS_LABEL[String(status[1])]?.toLowerCase()}`;
      return "updated a trip";
    }
    case "inventory.receive":
    case "inventory.issue":
    case "inventory.adjust":
    case "inventory.count": {
      const verb = { receive: "received", issue: "issued", adjust: "adjusted", count: "counted" }[
        e.action.split(".")[1]
      ];
      const delta = typeof m.delta === "string" ? Number(m.delta) : 0;
      const amount =
        `${Math.abs(delta).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${String(m.unit ?? "")}`.trim();
      const item = String(m.item ?? "an item");
      if (e.action === "inventory.count")
        return `counted ${item}: ${delta >= 0 ? "+" : "-"}${amount} against the records`;
      if (e.action === "inventory.adjust") return `adjusted ${item} by ${delta >= 0 ? "+" : "-"}${amount}`;
      return `${verb} ${amount} of ${item}`;
    }
    default:
      return e.action.replace(".", " ").replace("_", " ");
  }
}

function joinParts(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? "made a change";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/** ": amount 10.00 MAD → 12.00 MAD, date …" for value changes; field names only for text edits. */
function changesSuffix(m: Record<string, unknown>, format: Record<string, (v: unknown) => string>): string {
  const parts = Object.entries(m).map(([field, change]) => {
    const name = field === "expense_date" ? "date" : field === "description" ? "note" : field;
    if (!isChange(change)) return name;
    const f = format[field] ?? ((v: unknown) => String(v ?? "none"));
    return `${name} ${f(change[0])} → ${f(change[1])}`;
  });
  return parts.length ? ` (${parts.join(", ")})` : "";
}

const timeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export const formatWhen = (iso: string) => timeFmt.format(new Date(iso));
