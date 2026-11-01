import { AlertTriangle, ArrowRight, Boxes, CircleCheck, Loader2, Lock } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Organization, StockChangeKind, StockDraft, StockDraftLine } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatNumber } from "../lib/format";
import { NOTIFICATIONS_CHANGED } from "./AppShell";
import { FormAlert } from "./form";
import { isRtl, t } from "../i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<StockChangeKind, string> = {
  receive: t("Receive"),
  issue: t("Issue"),
  adjust: t("Adjust"),
  create: t("New item"),
  transfer: t("Transfer"),
  move: t("Move"),
  delete: t("Delete"),
};

const KIND_STYLE: Record<StockChangeKind, string> = {
  receive: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  issue: "bg-primary/10 text-primary",
  adjust: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  create: "bg-secondary text-secondary-foreground",
  transfer: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  move: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  delete: "bg-destructive/10 text-destructive",
};

const num = (s: string | null | undefined) => {
  const n = Number(String(s ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : NaN;
};

/**
 * Stock changes drafted by the assistant. Nothing has changed until the user confirms; they can untick lines
 * and correct quantities first. Lines the assistant couldn't match, or that need an owner or project
 * manager, can't be ticked.
 */
export function StockProposal({ draft, org }: { draft: StockDraft; org: Organization }) {
  const usable = (l: StockDraftLine) => !l.error && l.allowed;
  const [keep, setKeep] = useState(() => draft.lines.map(usable));
  // "20.00" from the server reads better as "20" in an input.
  const [qty, setQty] = useState(() => draft.lines.map((l) => (l.quantity === null ? "" : String(Number(l.quantity)))));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; line?: number } | null>(null);
  const [done, setDone] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);

  // Before/after again as quantities are edited; later lines on the same item follow from earlier ones.
  const preview = useMemo(() => {
    const running = new Map<number, number>();
    return draft.lines.map((l, i) => {
      if (l.error || l.kind === "create" || l.item_id === null) {
        return { before: l.on_hand_before, after: l.kind === "create" ? qty[i] || "0" : l.on_hand_after, negative: false };
      }
      const start = running.get(l.item_id) ?? num(l.on_hand_before);
      if (l.kind === "delete") {
        running.set(l.item_id, 0);
        return { before: String(start), after: "0", negative: false };
      }
      const q = num(qty[i]);
      const delta = l.kind === "transfer" ? 0 : l.kind === "issue" || l.kind === "move" ? -q : q;
      const after = keep[i] && Number.isFinite(q) ? start + delta : start;
      running.set(l.item_id, after);
      return { before: String(start), after: String(after), negative: after < 0 };
    });
  }, [draft.lines, qty, keep]);

  if (dismissed) return null;

  const chosen = draft.lines.map((l, i) => ({ l, i })).filter(({ i }) => keep[i]);
  const invalid = chosen.some(({ l, i }) => {
    const q = num(qty[i]);
    if (l.kind === "delete") return false;
    return !Number.isFinite(q) || (l.kind === "adjust" ? q === 0 : l.kind === "create" ? q < 0 : q <= 0) || preview[i].negative;
  });

  const confirm = async () => {
    setBusy(true);
    setError(null);
    const changes = chosen.map(({ l, i }) => {
      if (l.kind === "create") {
        return {
          kind: "create",
          name: l.name,
          unit: l.unit,
          sku: l.sku,
          location: l.location,
          unit_cost: l.unit_cost,
          reorder_level: l.reorder_level,
          quantity: qty[i] || "0",
          inventory_project_id: l.inventory_project_id,
          warehouse_id: l.warehouse_id,
        };
      }
      if (l.kind === "delete") return { kind: "delete", item_id: l.item_id };
      return {
        kind: l.kind,
        item_id: l.item_id,
        quantity: qty[i],
        warehouse_id: l.warehouse_id,
        to_warehouse_id: l.to_warehouse_id,
        to_project_id: l.to_project_id,
        project_id: l.project_id,
        note: l.note,
      };
    });
    try {
      await api(`/organizations/${org.id}/inventory/changes`, { body: { changes } });
      setDone(changes.length);
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED)); // a line may have triggered a low-stock alert
    } catch (e) {
      // The server names the failing line by its position among the confirmed ones.
      const at = e instanceof ApiError ? e.details?.line : undefined;
      setError({ message: errorMessage(e), line: typeof at === "number" ? chosen[at]?.i : undefined });
    } finally {
      setBusy(false);
    }
  };

  // The inventories these lines touch, for the "Open stock" link.
  const scopes = [...new Set(draft.lines.map((l) => l.inventory_project_id))];

  if (done !== null) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        role="status"
        className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm"
      >
        <CircleCheck className="size-5 text-emerald-600 dark:text-emerald-400" />
        <span className="flex-1 font-medium">{t("Stock updated: {count} changes saved.", { count: done })}</span>
        <Button asChild size="sm" variant="outline">
          <Link to={`/app/inventory${scopes.length === 1 ? `?scope=${scopes[0] ?? "general"}` : ""}`}>
            {t("Open stock")}
            <ArrowRight className="size-3.5 rtl:rotate-180" />
          </Link>
        </Button>
      </motion.div>
    );
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      aria-label={t("Stock changes, not saved yet")}
      className="mt-3 grid gap-4 rounded-xl border bg-card p-4 text-card-foreground shadow-sm"
    >
      <header className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Boxes className="size-4" />
        </span>
        <div className="grid gap-0.5">
          <h3 className="text-sm font-semibold">{t("Stock changes, not saved yet")}</h3>
          <p className="text-xs text-muted-foreground">
            {t("Check the quantities, untick anything you don't want, then confirm.")}
          </p>
        </div>
      </header>

      <ul className="grid gap-2">
        {draft.lines.map((l, i) => {
          const blocked = !usable(l);
          const p = preview[i];
          const highlight = error?.line === i;
          return (
            <li
              key={i}
              className={cn(
                "grid gap-2 rounded-lg border p-3 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center",
                blocked && "bg-muted/40",
                highlight && "border-destructive",
              )}
            >
              <Checkbox
                checked={keep[i]}
                disabled={blocked || busy}
                onCheckedChange={(v) => setKeep((k) => k.map((x, j) => (j === i ? v === true : x)))}
                aria-label={t("Include {name}", { name: l.name ?? "?" })}
              />
              <div className="grid min-w-0 gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className={cn("rounded-md border-0", KIND_STYLE[l.kind])}>
                    {KIND_LABEL[l.kind]}
                  </Badge>
                  <span className="truncate text-sm font-medium">{l.name ?? "?"}</span>
                  <span className="text-xs text-muted-foreground">{whereText(l)}</span>
                  {l.project_name && (
                    <span className="text-xs text-muted-foreground">{t("for {project}", { project: l.project_name })}</span>
                  )}
                </div>
                {l.note && <p className="text-xs text-muted-foreground">{l.note}</p>}
                {l.error ? (
                  <p className="flex items-center gap-1.5 text-xs text-destructive">
                    <AlertTriangle className="size-3.5" />
                    {l.error}
                  </p>
                ) : !l.allowed ? (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Lock className="size-3.5" />
                    {t("Only an owner or project manager can confirm this line.")}
                  </p>
                ) : (
                  p.after !== null && (
                    <p className="tabular flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" dir="ltr">
                      <span dir={isRtl() ? "rtl" : "ltr"}>{t("On hand")}</span>
                      <span>{formatNumber(p.before ?? "0")}</span>
                      <ArrowRight className="size-3" />
                      <span className={cn("font-medium text-foreground", p.negative && "text-destructive")}>
                        {formatNumber(p.after)} {l.unit}
                      </span>
                      {l.low_after && !p.negative && (
                        <span className="rounded bg-amber-500/15 px-1.5 py-px text-amber-700 dark:text-amber-300" dir={isRtl() ? "rtl" : "ltr"}>
                          {t("Low stock")}
                        </span>
                      )}
                    </p>
                  )
                )}
              </div>
              {!blocked && l.kind !== "delete" && (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="sr-only">{t("Quantity ({unit})", { unit: l.unit ?? "" })}</span>
                  <Input
                    value={qty[i]}
                    inputMode="decimal"
                    disabled={!keep[i] || busy}
                    onChange={(e) => setQty((q) => q.map((x, j) => (j === i ? e.target.value : x)))}
                    className="tabular h-8 w-24 text-end"
                  />
                  <span className="w-10 truncate">{l.unit}</span>
                </label>
              )}
            </li>
          );
        })}
      </ul>

      <FormAlert message={error?.message} />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setDismissed(true)} disabled={busy}>
          {t("Dismiss")}
        </Button>
        <Button type="button" size="sm" onClick={confirm} disabled={busy || chosen.length === 0 || invalid}>
          {busy && <Loader2 className="size-4 animate-spin" />}
          {t("Confirm {count} changes", { count: chosen.length })}
        </Button>
      </div>
    </motion.section>
  );
}

/** "Office move · Casablanca depot → Tangier store", in the reader's language. */
function whereText(l: StockDraftLine): string {
  const inventory = l.inventory_project_id === null ? t("General stock") : l.inventory_name;
  const here = l.warehouse_name ?? (l.kind === "transfer" ? t("Not in a warehouse") : null);
  if (l.kind === "transfer") {
    return `${inventory} · ${t("{from} to {to}", { from: here ?? t("Not in a warehouse"), to: l.to_warehouse_name ?? t("Not in a warehouse") })}`;
  }
  if (l.kind === "move") {
    const to = l.to_project_id === null ? t("General stock") : (l.to_inventory_name ?? "");
    return t("{from} to {to}", { from: [inventory, here].filter(Boolean).join(" · "), to: [to, l.to_warehouse_name].filter(Boolean).join(" · ") });
  }
  return [inventory, here].filter(Boolean).join(" · ");
}
