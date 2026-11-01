import { CircleCheck, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api/client";
import type { InventoryItem, Warehouse } from "../../api/models";
import { errorMessage } from "../../lib/errors";
import { formatMoney, formatNumber } from "../../lib/format";
import { FormAlert, FormField, SimpleSelect, TextField } from "../form";
import { t } from "../../i18n";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface CountResult {
  results: { item_id: number; name: string; unit: string; expected: string; counted: string; difference: string; warehouse: string | null }[];
  changed_count: number;
  value_change: string;
  currency: string;
}

/**
 * Count one place at a time (a warehouse, or stock that isn't in one): enter what's on the shelves; the
 * quantities there are set to it and the differences recorded. Items left empty aren't changed.
 */
export function StockCountDialog({
  open,
  onOpenChange,
  orgId,
  items,
  warehouses,
  onSaved,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  orgId: number;
  items: InventoryItem[];
  warehouses: Warehouse[];
  onSaved(): void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("Stock count")}</DialogTitle>
          <DialogDescription>
            {t("Enter what you count on the shelf. Items you leave empty aren't changed. Quantities are set to what you enter, and the differences are recorded.")}
          </DialogDescription>
        </DialogHeader>
        {open && <CountForm orgId={orgId} items={items} warehouses={warehouses} onSaved={onSaved} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function CountForm({
  orgId,
  items,
  warehouses,
  onSaved,
  onClose,
}: {
  orgId: number;
  items: InventoryItem[];
  warehouses: Warehouse[];
  onSaved(): void;
  onClose(): void;
}) {
  const [place, setPlace] = useState(warehouses[0] ? String(warehouses[0].id) : "");
  const [counts, setCounts] = useState<Record<number, string>>({});
  const [showExpected, setShowExpected] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CountResult | null>(null);

  const expectedAt = (item: InventoryItem) =>
    place === "" ? item.not_in_warehouse : (item.stock.find((s) => String(s.warehouse_id) === place)?.quantity ?? "0");
  const entered = useMemo(() => Object.entries(counts).filter(([, v]) => v.trim() !== ""), [counts]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<CountResult>(`/organizations/${orgId}/inventory/counts`, {
        body: {
          counts: entered.map(([id, v]) => ({ item_id: Number(id), counted: v.trim().replace(",", "."), warehouse_id: place ? Number(place) : null })),
          note: note.trim() || null,
        },
      });
      setResult(r);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    const changed = result.results.filter((r) => Number(r.difference) !== 0);
    return (
      <div className="grid gap-4" role="status">
        <p className="flex items-center gap-2 font-medium">
          <CircleCheck className="size-5 text-emerald-600 dark:text-emerald-400" />
          {result.changed_count === 0
            ? t("{count} items counted, no differences.", { count: result.results.length })
            : t("{count} items counted, {changed} different from the records.", { count: result.results.length, changed: result.changed_count })}
        </p>
        {result.changed_count > 0 && (
          <p className="text-sm text-muted-foreground">
            {t("Stock value changed by {amount}.", { amount: formatMoney(result.value_change, result.currency) })}
          </p>
        )}
        {changed.length > 0 && (
          <ul className="grid gap-1 text-sm">
            {changed.map((r) => (
              <li key={r.item_id} className="tabular flex justify-between gap-3 rounded-md bg-muted/50 px-3 py-1.5">
                <span>{r.name}</span>
                <span className={Number(r.difference) < 0 ? "text-destructive" : "text-emerald-600 dark:text-emerald-400"}>
                  {Number(r.difference) > 0 ? "+" : ""}
                  {formatNumber(r.difference)} {r.unit}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end">
          <Button onClick={onClose}>{t("Done")}</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <FormAlert message={error} />
      <div className="flex flex-wrap items-end gap-4">
        <FormField id="count_place" label={t("Counting")} className="min-w-56 flex-1">
          <SimpleSelect
            id="count_place"
            value={place}
            onChange={(v) => {
              setPlace(v);
              setCounts({});
            }}
            options={[
              ...warehouses.map((w) => ({ value: String(w.id), label: w.name })),
              { value: "", label: t("Not in a warehouse") },
            ]}
          />
        </FormField>
        <div className="flex items-center gap-2 pb-2">
          <Checkbox id="count_expected" checked={showExpected} onCheckedChange={(v) => setShowExpected(v === true)} />
          <Label htmlFor="count_expected" className="font-normal">
            {t("Show expected quantities")}
          </Label>
        </div>
      </div>
      <div className="max-h-[45vh] overflow-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-muted/80 text-xs text-muted-foreground backdrop-blur">
            <tr>
              <th className="px-3 py-2 text-start font-medium">{t("Item")}</th>
              {showExpected && <th className="px-3 py-2 text-end font-medium">{t("Expected")}</th>}
              <th className="px-3 py-2 text-end font-medium">{t("Counted")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} className="border-t">
                <td className="px-3 py-1.5">{i.name}</td>
                {showExpected && (
                  <td className="tabular px-3 py-1.5 text-end text-muted-foreground">
                    {formatNumber(expectedAt(i))} {i.unit}
                  </td>
                )}
                <td className="px-3 py-1.5">
                  <div className="flex items-center justify-end gap-2">
                    <Input
                      value={counts[i.id] ?? ""}
                      inputMode="decimal"
                      onChange={(e) => setCounts((c) => ({ ...c, [i.id]: e.target.value }))}
                      aria-label={t("Counted {unit} of {name}", { unit: i.unit, name: i.name })}
                      className="tabular h-8 w-24 text-end"
                    />
                    <span className="w-10 truncate text-xs text-muted-foreground">{i.unit}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TextField id="count_note" label={t("Note")} value={note} onChange={(e) => setNote(e.target.value)} hint={t("Defaults to \"Stock count\".")} maxLength={500} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          {t("Cancel")}
        </Button>
        <Button onClick={save} disabled={busy || entered.length === 0}>
          {busy && <Loader2 className="size-4 animate-spin" />}
          {t("Save count ({count})", { count: entered.length })}
        </Button>
      </div>
    </div>
  );
}
