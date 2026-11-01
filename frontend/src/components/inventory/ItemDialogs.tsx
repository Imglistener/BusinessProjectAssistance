import { ArrowRight, Loader2 } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api } from "../../api/client";
import type { InventoryItem, Movement, Project, Warehouse } from "../../api/models";
import { formatWhen } from "../../lib/activity";
import { errorMessage } from "../../lib/errors";
import { formatNumber } from "../../lib/format";
import { FormAlert, FormField, SimpleSelect, TextField } from "../form";
import { isRtl, t } from "../../i18n";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

/** "" = not in a warehouse; otherwise a warehouse ID. */
type Place = string;
const NOWHERE = "";

const placeValue = (id: number | null | undefined): Place => (id ? String(id) : NOWHERE);
const placeId = (p: Place): number | null => (p === NOWHERE ? null : Number(p));

/** How much of the item is at a place, as text ("12"). */
function atPlace(item: InventoryItem, place: Place): string {
  if (place === NOWHERE) return item.not_in_warehouse;
  return item.stock.find((s) => String(s.warehouse_id) === place)?.quantity ?? "0";
}

function placeOptions(warehouses: Warehouse[], item?: InventoryItem, withQuantities = false) {
  const label = (name: string, place: Place) =>
    withQuantities && item ? `${name} (${formatNumber(atPlace(item, place))} ${item.unit})` : name;
  return [
    { value: NOWHERE, label: label(t("Not in a warehouse"), NOWHERE) },
    ...warehouses.map((w) => ({ value: String(w.id), label: label(w.name, String(w.id)) })),
  ];
}

function Shell({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {open && children}
      </DialogContent>
    </Dialog>
  );
}

function Actions({ busy, label, onCancel, disabled }: { busy: boolean; label: string; onCancel(): void; disabled?: boolean }) {
  return (
    <div className="flex justify-end gap-2 pt-1">
      <Button type="button" variant="ghost" onClick={onCancel}>
        {t("Cancel")}
      </Button>
      <Button type="submit" disabled={busy || disabled}>
        {busy && <Loader2 className="size-4 animate-spin" />}
        {label}
      </Button>
    </div>
  );
}

/** Runs a request for a form and reports errors; the caller closes and refreshes on success. */
function useAction(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (e: FormEvent, request: () => Promise<unknown>) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await request();
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

// ---------- add / edit an item ----------

export function ItemFormDialog({
  open,
  onOpenChange,
  orgId,
  projectId,
  item,
  warehouses,
  currency,
  onSaved,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  orgId: number;
  projectId: number | null;
  item: InventoryItem | null;
  warehouses: Warehouse[];
  currency: string;
  onSaved(): void;
}) {
  return (
    <Shell open={open} onOpenChange={onOpenChange} title={item ? t("Edit item") : t("Add item")}>
      <ItemForm orgId={orgId} projectId={projectId} item={item} warehouses={warehouses} currency={currency}
        onSaved={onSaved} onCancel={() => onOpenChange(false)} />
    </Shell>
  );
}

function ItemForm({
  orgId,
  projectId,
  item,
  warehouses,
  currency,
  onSaved,
  onCancel,
}: {
  orgId: number;
  projectId: number | null;
  item: InventoryItem | null;
  warehouses: Warehouse[];
  currency: string;
  onSaved(): void;
  onCancel(): void;
}) {
  const [f, setF] = useState({
    name: item?.name ?? "",
    sku: item?.sku ?? "",
    unit: item?.unit ?? "pcs",
    unit_cost: item?.unit_cost ?? "",
    reorder_level: item?.reorder_level ?? "",
    location: item?.location ?? "",
    quantity: "",
    warehouse: NOWHERE as Place,
  });
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const { busy, error, run } = useAction(onSaved);
  const num = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) =>
        run(e, () => {
          const body: Record<string, unknown> = {
            name: f.name.trim(),
            sku: f.sku.trim() || null,
            unit: f.unit.trim() || "pcs",
            unit_cost: num(f.unit_cost),
            reorder_level: num(f.reorder_level),
            location: f.location.trim() || null,
          };
          if (item) return api(`/inventory/${item.id}`, { method: "PATCH", body });
          return api(`/organizations/${orgId}/inventory`, {
            body: { ...body, project_id: projectId, quantity: num(f.quantity), warehouse_id: placeId(f.warehouse) },
          });
        })
      }
    >
      <FormAlert message={error} />
      <TextField id="item_name" label={t("Name")} value={f.name} onChange={(e) => set("name")(e.target.value)} required maxLength={200} autoFocus />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField id="item_sku" label={t("SKU")} value={f.sku} onChange={(e) => set("sku")(e.target.value)} maxLength={60} />
        <TextField id="item_unit" label={t("Unit")} value={f.unit} onChange={(e) => set("unit")(e.target.value)} placeholder={t("pcs, box, kg, litre…")} maxLength={20} />
        <TextField id="item_cost" label={t("Unit cost ({default_currency})", { default_currency: currency })} value={f.unit_cost}
          onChange={(e) => set("unit_cost")(e.target.value)} inputMode="decimal" className="tabular" />
        <TextField id="item_reorder" label={t("Reorder level")} value={f.reorder_level} onChange={(e) => set("reorder_level")(e.target.value)}
          inputMode="decimal" hint={t("Warn when stock gets this low.")} className="tabular" />
      </div>
      <TextField id="item_location" label={t("Spot in the warehouse")} value={f.location} onChange={(e) => set("location")(e.target.value)}
        placeholder={t("e.g. Aisle 3, shelf B")} maxLength={120} />
      {!item && (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField id="item_quantity" label={t("Opening stock")} value={f.quantity} onChange={(e) => set("quantity")(e.target.value)}
            inputMode="decimal" hint={t("How many you have now. Leave empty for zero.")} className="tabular" />
          <FormField id="item_warehouse" label={t("Warehouse")}>
            <SimpleSelect id="item_warehouse" value={f.warehouse} onChange={set("warehouse")} options={placeOptions(warehouses)} />
          </FormField>
        </div>
      )}
      <Actions busy={busy} label={item ? t("Save changes") : t("Add item")} onCancel={onCancel} disabled={!f.name.trim()} />
    </form>
  );
}

// ---------- receive / issue / adjust ----------

export type MovementKind = "receive" | "issue" | "adjust";

export function MovementDialog({
  open,
  onOpenChange,
  kind,
  item,
  warehouses,
  projects,
  onSaved,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  kind: MovementKind;
  item: InventoryItem;
  warehouses: Warehouse[];
  projects: Project[];
  onSaved(): void;
}) {
  const title = { receive: t("Receive stock"), issue: t("Issue stock"), adjust: t("Adjust stock") }[kind];
  return (
    <Shell open={open} onOpenChange={onOpenChange} title={title} description={item.name}>
      <MovementForm kind={kind} item={item} warehouses={warehouses} projects={projects} onSaved={onSaved} onCancel={() => onOpenChange(false)} />
    </Shell>
  );
}

function MovementForm({
  kind,
  item,
  warehouses,
  projects,
  onSaved,
  onCancel,
}: {
  kind: MovementKind;
  item: InventoryItem;
  warehouses: Warehouse[];
  projects: Project[];
  onSaved(): void;
  onCancel(): void;
}) {
  // Start where the stock is: the only warehouse holding it, if there's just one.
  const [place, setPlace] = useState<Place>(item.stock.length === 1 && kind !== "receive" ? String(item.stock[0].warehouse_id) : NOWHERE);
  const [qty, setQty] = useState("");
  const [project, setProject] = useState("");
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction(onSaved);
  const general = item.project_id === null;

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) =>
        run(e, () =>
          api(`/inventory/${item.id}/movements`, {
            body: {
              kind,
              quantity: qty.trim().replace(",", "."),
              warehouse_id: placeId(place),
              project_id: kind === "issue" && general && project ? Number(project) : null,
              note: note.trim() || null,
            },
          }),
        )
      }
    >
      <FormAlert message={error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id="move_qty"
          label={kind === "adjust" ? t("Change ({unit}, use - to remove)", { unit: item.unit }) : t("Quantity ({unit})", { unit: item.unit })}
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          inputMode="decimal"
          required
          autoFocus
          className="tabular"
        />
        <FormField id="move_place" label={kind === "receive" ? t("Into") : t("From")}>
          <SimpleSelect id="move_place" value={place} onChange={setPlace} options={placeOptions(warehouses, item, kind !== "receive")} />
        </FormField>
      </div>
      {kind === "issue" && general && (
        <FormField id="move_project" label={t("For project")}>
          <SimpleSelect id="move_project" value={project} onChange={setProject}
            options={[{ value: "", label: t("No project") }, ...projects.map((p) => ({ value: String(p.id), label: p.name }))]} />
        </FormField>
      )}
      <TextField id="move_note" label={kind === "adjust" ? t("Reason") : t("Note")} value={note} onChange={(e) => setNote(e.target.value)}
        required={kind === "adjust"} maxLength={500} />
      <p className="tabular text-xs text-muted-foreground">
        {t("On hand now: {quantity}.", { quantity: `${formatNumber(item.quantity_on_hand)} ${item.unit}` })}
      </p>
      <Actions busy={busy} label={{ receive: t("Receive stock"), issue: t("Issue stock"), adjust: t("Adjust stock") }[kind]} onCancel={onCancel} />
    </form>
  );
}

// ---------- transfer between warehouses ----------

export function TransferDialog({
  open,
  onOpenChange,
  item,
  warehouses,
  onSaved,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  item: InventoryItem;
  warehouses: Warehouse[];
  onSaved(): void;
}) {
  return (
    <Shell open={open} onOpenChange={onOpenChange} title={t("Transfer between warehouses")} description={item.name}>
      <TransferForm item={item} warehouses={warehouses} onSaved={onSaved} onCancel={() => onOpenChange(false)} />
    </Shell>
  );
}

function TransferForm({ item, warehouses, onSaved, onCancel }: { item: InventoryItem; warehouses: Warehouse[]; onSaved(): void; onCancel(): void }) {
  const first = item.stock[0] ? String(item.stock[0].warehouse_id) : NOWHERE;
  const [from, setFrom] = useState<Place>(first);
  const [to, setTo] = useState<Place>(placeValue(warehouses.find((w) => String(w.id) !== first)?.id));
  const [qty, setQty] = useState("");
  const { busy, error, run } = useAction(onSaved);
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) =>
        run(e, () =>
          api(`/inventory/${item.id}/transfers`, {
            body: { quantity: qty.trim().replace(",", "."), from_warehouse_id: placeId(from), to_warehouse_id: placeId(to) },
          }),
        )
      }
    >
      <FormAlert message={error} />
      <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <FormField id="transfer_from" label={t("From")}>
          <SimpleSelect id="transfer_from" value={from} onChange={setFrom} options={placeOptions(warehouses, item, true)} />
        </FormField>
        <ArrowRight className={`mb-2.5 hidden size-4 text-muted-foreground sm:block ${isRtl() ? "rotate-180" : ""}`} />
        <FormField id="transfer_to" label={t("To")}>
          <SimpleSelect id="transfer_to" value={to} onChange={setTo} options={placeOptions(warehouses, item, true)} />
        </FormField>
      </div>
      <TextField id="transfer_qty" label={t("Quantity ({unit})", { unit: item.unit })} value={qty} onChange={(e) => setQty(e.target.value)}
        inputMode="decimal" required autoFocus className="tabular" />
      <Actions busy={busy} label={t("Transfer")} onCancel={onCancel} disabled={from === to} />
    </form>
  );
}

// ---------- move to another inventory ----------

export function MoveDialog({
  open,
  onOpenChange,
  orgId,
  item,
  warehouses,
  projects,
  onSaved,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  orgId: number;
  item: InventoryItem;
  warehouses: Warehouse[];
  projects: Project[];
  onSaved(): void;
}) {
  return (
    <Shell open={open} onOpenChange={onOpenChange} title={t("Move to another inventory")} description={item.name}>
      <MoveForm orgId={orgId} item={item} warehouses={warehouses} projects={projects} onSaved={onSaved} onCancel={() => onOpenChange(false)} />
    </Shell>
  );
}

function MoveForm({
  orgId,
  item,
  warehouses,
  projects,
  onSaved,
  onCancel,
}: {
  orgId: number;
  item: InventoryItem;
  warehouses: Warehouse[];
  projects: Project[];
  onSaved(): void;
  onCancel(): void;
}) {
  const targets = [
    ...(item.project_id !== null ? [{ value: "general", label: t("General stock") }] : []),
    ...projects.filter((p) => p.id !== item.project_id && p.status !== "archived").map((p) => ({ value: String(p.id), label: p.name })),
  ];
  const [target, setTarget] = useState(targets[0]?.value ?? "");
  const [from, setFrom] = useState<Place>(item.stock.length === 1 ? String(item.stock[0].warehouse_id) : NOWHERE);
  const [to, setTo] = useState<Place>(NOWHERE);
  const [targetWarehouses, setTargetWarehouses] = useState<Warehouse[] | null>(null);
  const [qty, setQty] = useState("");
  const { busy, error, run } = useAction(onSaved);

  useEffect(() => {
    if (!target) return;
    setTargetWarehouses(null);
    setTo(NOWHERE);
    api<{ warehouses: Warehouse[] }>(`/organizations/${orgId}/warehouses?scope=${target}`)
      .then((r) => setTargetWarehouses(r.warehouses))
      .catch(() => setTargetWarehouses([]));
  }, [orgId, target]);

  if (targets.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("There's no other inventory to move it to yet.")}</p>;
  }
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) =>
        run(e, () =>
          api(`/inventory/${item.id}/move`, {
            body: {
              to_project_id: target === "general" ? null : Number(target),
              quantity: qty.trim().replace(",", "."),
              from_warehouse_id: placeId(from),
              to_warehouse_id: placeId(to),
            },
          }),
        )
      }
    >
      <FormAlert message={error} />
      <FormField id="move_target" label={t("Move to")}>
        <SimpleSelect id="move_target" value={target} onChange={setTarget} options={targets} />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="move_from" label={t("Take from")}>
          <SimpleSelect id="move_from" value={from} onChange={setFrom} options={placeOptions(warehouses, item, true)} />
        </FormField>
        <FormField id="move_into" label={t("Put into")}>
          {targetWarehouses === null ? (
            <Skeleton className="h-9" />
          ) : (
            <SimpleSelect id="move_into" value={to} onChange={setTo} options={placeOptions(targetWarehouses)} />
          )}
        </FormField>
      </div>
      <TextField id="move_qty2" label={t("Quantity ({unit})", { unit: item.unit })} value={qty} onChange={(e) => setQty(e.target.value)}
        inputMode="decimal" required className="tabular"
        hint={t("The item there is found by name, or added if it isn't in that inventory yet.")} />
      <Actions busy={busy} label={t("Move stock")} onCancel={onCancel} />
    </form>
  );
}

// ---------- history ----------

const KIND_LABEL: Record<Movement["kind"], string> = {
  receive: t("Received"),
  issue: t("Issued"),
  adjust: t("Adjusted"),
  count: t("Counted"),
  transfer: t("Transferred"),
  move_out: t("Moved out"),
  move_in: t("Moved in"),
};

export function HistoryDialog({ open, onOpenChange, item }: { open: boolean; onOpenChange(open: boolean): void; item: InventoryItem }) {
  const [rows, setRows] = useState<Movement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    setRows(null);
    api<{ movements: Movement[] }>(`/inventory/${item.id}/movements?limit=50`)
      .then((r) => setRows(r.movements))
      .catch((e) => setError(errorMessage(e, t("Couldn't load the history."))));
  }, [open, item.id]);
  return (
    <Shell open={open} onOpenChange={onOpenChange} title={t("History")} description={item.name}>
      <FormAlert message={error} />
      {!rows && !error && <Skeleton className="h-32" />}
      {rows && rows.length === 0 && <p className="text-sm text-muted-foreground">{t("No changes recorded yet.")}</p>}
      {rows && rows.length > 0 && (
        <ol className="grid max-h-[60vh] gap-2 overflow-auto">
          {rows.map((m) => (
            <li key={m.id} className="grid gap-0.5 rounded-lg border p-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium">
                  {KIND_LABEL[m.kind]}{" "}
                  <span className="tabular">
                    {m.kind === "transfer" ? "" : Number(m.quantity_delta) > 0 ? "+" : ""}
                    {formatNumber(m.quantity_delta)} {item.unit}
                  </span>
                </span>
                <time className="text-xs text-muted-foreground" dateTime={m.created_at}>
                  {formatWhen(m.created_at)}
                </time>
              </div>
              <p className="text-xs text-muted-foreground">
                {[
                  m.kind === "transfer"
                    ? t("{from} to {to}", { from: m.warehouse ?? t("Not in a warehouse"), to: m.to_warehouse ?? t("Not in a warehouse") })
                    : m.warehouse,
                  m.kind !== "transfer" && t("leaving {quantity}", { quantity: `${formatNumber(m.quantity_after)} ${item.unit}` }),
                  m.project_name && t("for {project}", { project: m.project_name }),
                  m.note,
                  m.created_by,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </li>
          ))}
        </ol>
      )}
    </Shell>
  );
}

// ---------- delete ----------

export function DeleteItemDialog({ item, onClose, onDeleted }: { item: InventoryItem | null; onClose(): void; onDeleted(): void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <AlertDialog open={item !== null} onOpenChange={(o) => !o && !busy && (setError(null), onClose())}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("Delete {name}?", { name: item?.name ?? "" })}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("The item, its stock ({quantity}) and its history are removed for good. To keep the history, archive it instead.", {
              quantity: item ? `${formatNumber(item.quantity_on_hand)} ${item.unit}` : "",
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <FormAlert message={error} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t("Cancel")}</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            className="bg-destructive text-white hover:bg-destructive/90"
            onClick={async (e) => {
              e.preventDefault();
              if (!item) return;
              setBusy(true);
              try {
                await api(`/inventory/${item.id}`, { method: "DELETE" });
                onDeleted();
                onClose();
              } catch (err) {
                setError(errorMessage(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy && <Loader2 className="size-4 animate-spin" />}
            {t("Delete item")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
