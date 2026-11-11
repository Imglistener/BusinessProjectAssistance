import { AlertTriangle, ArrowRight, CircleCheck, CircleX, ListChecks, Loader2, Lock } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { api } from "../api/client";
import type { ActionDraft, ActionDraftLine, ActionKind } from "../api/models";
import { errorMessage } from "../lib/errors";
import { PRIORITY_LABEL, STATUS_LABEL, TASK_STATUS_LABEL, TRIP_STATUS_LABEL, formatDate, formatMoney } from "../lib/format";
import { NOTIFICATIONS_CHANGED } from "./AppShell";
import { t } from "../i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<ActionKind, string> = {
  update_project: t("Edit project"),
  archive_project: t("Archive project"),
  restore_project: t("Restore project"),
  create_task: t("New task"),
  update_task: t("Update task"),
  create_milestone: t("New milestone"),
  update_milestone: t("Update milestone"),
  delete_milestone: t("Delete milestone"),
  add_expense: t("New expense"),
  void_expense: t("Void expense"),
  create_trip: t("New trip"),
  update_trip: t("Update trip"),
  refresh_fuel_prices: t("Refresh fuel prices"),
  set_fuel_price: t("Set fuel price"),
  mark_notifications_read: t("Mark notifications as read"),
};

const DANGER: ActionKind[] = ["archive_project", "delete_milestone", "void_expense"];

const FIELD_LABEL: Record<string, string> = {
  name: t("Name"),
  description: t("Description"),
  budget: t("Budget"),
  start_date: t("Start"),
  end_date: t("End"),
  status: t("Status"),
  milestone_status: t("Status"),
  trip_status: t("Status"),
  expense_status: t("Status"),
  title: t("Title"),
  due_date: t("Due"),
  priority: t("Priority"),
  assignee: t("Assignee"),
  milestone: t("Milestone"),
  category: t("Category"),
  amount: t("Amount"),
  expense_date: t("Date"),
  destination: t("Destination"),
  purpose: t("Purpose"),
  fuel_type: t("Fuel"),
  price_per_litre: t("Per litre"),
  city: t("City"),
};

const VALUE_LABEL: Record<string, Record<string, string>> = {
  status: { ...STATUS_LABEL, ...TASK_STATUS_LABEL },
  milestone_status: { open: t("Open"), done: t("Done") },
  trip_status: TRIP_STATUS_LABEL,
  expense_status: { valid: t("Valid"), voided: t("Voided"), refunded: t("Refunded") },
  priority: PRIORITY_LABEL,
  fuel_type: { diesel: t("Diesel"), petrol: t("Petrol") },
};

/** A field's value as the reader expects it: translated statuses, local dates and money. */
function show(field: string, value: string | null, line: ActionDraftLine): string {
  if (value === null || value === "") return "—";
  if (VALUE_LABEL[field]?.[value]) return VALUE_LABEL[field][value];
  if (/date$/.test(field)) return formatDate(value);
  if (["budget", "amount", "price_per_litre"].includes(field)) return formatMoney(value, line.currency ?? "MAD");
  return value;
}

type Outcome = { ok: true } | { ok: false; message: string };

/**
 * Changes the assistant drafted (tasks, milestones, projects, expenses, trips, fuel prices, notifications).
 * Nothing has changed until the user confirms. Each confirmed line is sent to the app's own API with the user's
 * session, one after the other, so the usual permission checks apply; each line then shows how it went.
 */
export function ActionProposal({ draft }: { draft: ActionDraft }) {
  const usable = (l: ActionDraftLine) => !l.error && l.allowed && l.request !== null;
  const [keep, setKeep] = useState(() => draft.lines.map(usable));
  const [busy, setBusy] = useState(false);
  const [outcomes, setOutcomes] = useState<(Outcome | null)[] | null>(null);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;
  const chosen = draft.lines.map((l, i) => ({ l, i })).filter(({ l, i }) => keep[i] && usable(l));

  const confirm = async () => {
    setBusy(true);
    const results: (Outcome | null)[] = draft.lines.map(() => null);
    for (const { l, i } of chosen) {
      const r = l.request!;
      try {
        await api(r.path, { method: r.method, body: r.body ?? undefined });
        results[i] = { ok: true };
      } catch (e) {
        results[i] = { ok: false, message: errorMessage(e) };
      }
      setOutcomes([...results]);
    }
    setBusy(false);
    window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
  };

  const finished = outcomes !== null && !busy;
  const done = outcomes?.filter((o) => o?.ok).length ?? 0;
  const failed = outcomes?.filter((o) => o && !o.ok).length ?? 0;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      aria-label={t("Changes, not saved yet")}
      className="mt-3 grid gap-4 rounded-xl border bg-card p-4 text-card-foreground shadow-sm"
    >
      <header className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <ListChecks className="size-4" />
        </span>
        <div className="grid gap-0.5">
          <h3 className="text-sm font-semibold">{finished ? t("Changes") : t("Changes, not saved yet")}</h3>
          <p className="text-xs text-muted-foreground">
            {finished
              ? t("{done} saved, {failed} not saved.", { done, failed })
              : t("Untick anything you don't want, then confirm. Each change uses your own permissions.")}
          </p>
        </div>
      </header>

      <ul className="grid gap-2">
        {draft.lines.map((l, i) => {
          const blocked = !usable(l);
          const outcome = outcomes?.[i] ?? null;
          return (
            <li
              key={i}
              className={cn(
                "grid gap-2 rounded-lg border p-3 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-start",
                blocked && "bg-muted/40",
                outcome && !outcome.ok && "border-destructive",
              )}
            >
              {outcome ? (
                outcome.ok ? (
                  <CircleCheck className="mt-0.5 size-4 text-emerald-600 dark:text-emerald-400" aria-label={t("Saved")} />
                ) : (
                  <CircleX className="mt-0.5 size-4 text-destructive" aria-label={t("Not saved")} />
                )
              ) : (
                <Checkbox
                  checked={keep[i]}
                  disabled={blocked || busy || outcomes !== null}
                  onCheckedChange={(v) => setKeep((k) => k.map((x, j) => (j === i ? v === true : x)))}
                  aria-label={t("Include {name}", { name: l.target ?? KIND_LABEL[l.kind] ?? l.kind })}
                />
              )}
              <div className="grid min-w-0 gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant="secondary"
                    className={cn("rounded-md border-0", DANGER.includes(l.kind) ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary")}
                  >
                    {KIND_LABEL[l.kind] ?? l.kind}
                  </Badge>
                  {l.target && <span className="truncate text-sm font-medium">{l.target}</span>}
                  {l.project_name && l.project_name !== l.target && (
                    <span className="text-xs text-muted-foreground">{l.project_name}</span>
                  )}
                </div>
                {l.changes.length > 0 && (
                  <ul className="grid gap-0.5 text-xs text-muted-foreground">
                    {l.changes.map((c, j) => (
                      <li key={j} className="flex flex-wrap items-center gap-1.5">
                        <span>{FIELD_LABEL[c.field] ?? c.field}</span>
                        {c.before !== null && (
                          <>
                            <span>{show(c.field, c.before, l)}</span>
                            <ArrowRight className="size-3 rtl:rotate-180" />
                          </>
                        )}
                        <span className="font-medium text-foreground">{show(c.field, c.after, l)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {outcome && !outcome.ok ? (
                  <p className="flex items-center gap-1.5 text-xs text-destructive">
                    <AlertTriangle className="size-3.5" />
                    {outcome.message}
                  </p>
                ) : l.error ? (
                  <p className="flex items-center gap-1.5 text-xs text-destructive">
                    <AlertTriangle className="size-3.5" />
                    {l.error}
                  </p>
                ) : (
                  !l.allowed && (
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Lock className="size-3.5" />
                      {t("Your role can't make this change.")}
                    </p>
                  )
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {outcomes === null && (
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={() => setDismissed(true)} disabled={busy}>
            {t("Dismiss")}
          </Button>
          <Button type="button" size="sm" onClick={confirm} disabled={busy || chosen.length === 0}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {t("Confirm {count} changes", { count: chosen.length })}
          </Button>
        </div>
      )}
      {busy && outcomes !== null && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
          <Loader2 className="size-3.5 animate-spin" />
          {t("Saving…")}
        </p>
      )}
    </motion.section>
  );
}
