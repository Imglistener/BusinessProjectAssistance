import { Loader2, MapPin, Pencil, Plus, Trash2, Warehouse as WarehouseIcon } from "lucide-react";
import { motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { Warehouse } from "../../api/models";
import { errorMessage } from "../../lib/errors";
import { formatMoney, formatNumber } from "../../lib/format";
import { FormAlert, FormField, TextField } from "../form";
import { LocationPicker, type Location } from "./LocationPicker";
import { t } from "../../i18n";
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
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

/** The warehouses of one inventory (General stock or a project's): where they are and what they hold. */
export function Warehouses({
  orgId,
  projectId,
  warehouses,
  currency,
  canManage,
  onChanged,
}: {
  orgId: number;
  projectId: number | null;
  warehouses: Warehouse[];
  currency: string;
  canManage: boolean;
  onChanged(): void;
}) {
  const [editing, setEditing] = useState<Warehouse | "new" | null>(null);
  const [deleting, setDeleting] = useState<Warehouse | null>(null);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {t("Where this inventory's stock is kept. Items can be split across several warehouses.")}
        </p>
        {canManage && (
          <Button onClick={() => setEditing("new")}>
            <Plus className="size-4" />
            {t("Add warehouse")}
          </Button>
        )}
      </div>

      {warehouses.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="grid justify-items-center gap-2 py-10 text-center">
            <span className="flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <WarehouseIcon className="size-5" />
            </span>
            <p className="font-medium">{t("No warehouses yet")}</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              {t("Add the places where you keep stock, then receive or move items into them.")}
            </p>
          </CardContent>
        </Card>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {warehouses.map((w, i) => (
            <motion.li
              key={w.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.04 }}
            >
              <Card className="h-full gap-3 py-5">
                <CardContent className="grid gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="grid min-w-0 gap-1">
                      <h3 className="warehouse-name truncate font-semibold">{w.name}</h3>
                      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                        <MapPin className="mt-px size-3.5 shrink-0" />
                        <span className="line-clamp-2">{w.address || t("No address yet")}</span>
                      </p>
                    </div>
                    {canManage && (
                      <div className="flex shrink-0 gap-1">
                        <Button variant="ghost" size="icon" className="size-8" onClick={() => setEditing(w)} aria-label={t("Edit {name}", { name: w.name })}>
                          <Pencil className="size-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="size-8 text-destructive hover:text-destructive" onClick={() => setDeleting(w)} aria-label={t("Delete {name}", { name: w.name })}>
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                  <dl className="grid grid-cols-[1fr_1fr_2fr] gap-2 rounded-lg bg-muted/50 p-3 text-center">
                    <div>
                      <dt className="text-[11px] text-muted-foreground">{t("Items")}</dt>
                      <dd className="tabular font-semibold">{w.item_count}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] text-muted-foreground">{t("Units")}</dt>
                      <dd className="tabular font-semibold">{formatNumber(w.units)}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] text-muted-foreground">{t("Value")}</dt>
                      <dd className="tabular whitespace-nowrap text-sm font-semibold leading-6">{formatMoney(w.value, currency)}</dd>
                    </div>
                  </dl>
                  {w.notes && <p className="text-xs text-muted-foreground">{w.notes}</p>}
                  {w.lat !== null && w.lng !== null && (
                    <a
                      className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                      href={`https://www.openstreetmap.org/?mlat=${w.lat}&mlon=${w.lng}#map=16/${w.lat}/${w.lng}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t("Open in OpenStreetMap")}
                    </a>
                  )}
                </CardContent>
              </Card>
            </motion.li>
          ))}
        </ul>
      )}

      <WarehouseDialog
        orgId={orgId}
        projectId={projectId}
        warehouse={editing === "new" ? null : editing}
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        onSaved={() => {
          setEditing(null);
          onChanged();
        }}
      />
      <DeleteWarehouseDialog warehouse={deleting} onClose={() => setDeleting(null)} onDeleted={onChanged} />
    </div>
  );
}

function WarehouseDialog({
  orgId,
  projectId,
  warehouse,
  open,
  onOpenChange,
  onSaved,
}: {
  orgId: number;
  projectId: number | null;
  warehouse: Warehouse | null;
  open: boolean;
  onOpenChange(open: boolean): void;
  onSaved(): void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{warehouse ? t("Edit warehouse") : t("Add warehouse")}</DialogTitle>
          <DialogDescription>{t("Give it a name and pin it on the map.")}</DialogDescription>
        </DialogHeader>
        {open && <WarehouseForm orgId={orgId} projectId={projectId} warehouse={warehouse} onSaved={onSaved} onCancel={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function WarehouseForm({
  orgId,
  projectId,
  warehouse,
  onSaved,
  onCancel,
}: {
  orgId: number;
  projectId: number | null;
  warehouse: Warehouse | null;
  onSaved(): void;
  onCancel(): void;
}) {
  const [name, setName] = useState(warehouse?.name ?? "");
  const [notes, setNotes] = useState(warehouse?.notes ?? "");
  const [location, setLocation] = useState<Location>({
    address: warehouse?.address ?? "",
    lat: warehouse?.lat ?? null,
    lng: warehouse?.lng ?? null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      address: location.address.trim() || null,
      lat: location.lat,
      lng: location.lng,
      notes: notes.trim() || null,
    };
    try {
      if (warehouse) await api(`/warehouses/${warehouse.id}`, { method: "PATCH", body });
      else await api(`/organizations/${orgId}/warehouses`, { body: { ...body, project_id: projectId } });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} className="grid gap-4">
      <FormAlert message={error} />
      <TextField id="warehouse_name" label={t("Name")} value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoFocus />
      <FormField id="warehouse_address" label={t("Address")}>
        <Textarea
          id="warehouse_address"
          rows={2}
          value={location.address}
          maxLength={300}
          onChange={(e) => setLocation((l) => ({ ...l, address: e.target.value }))}
        />
      </FormField>
      <LocationPicker value={location} onChange={setLocation} />
      <TextField id="warehouse_notes" label={t("Notes")} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("Cancel")}
        </Button>
        <Button type="submit" disabled={busy || !name.trim()}>
          {busy && <Loader2 className="size-4 animate-spin" />}
          {t("Save warehouse")}
        </Button>
      </div>
    </form>
  );
}

function DeleteWarehouseDialog({ warehouse, onClose, onDeleted }: { warehouse: Warehouse | null; onClose(): void; onDeleted(): void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const holdsStock = !!warehouse && Number(warehouse.units) !== 0;
  return (
    <AlertDialog open={warehouse !== null} onOpenChange={(o) => !o && !busy && (setError(null), onClose())}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("Delete {name}?", { name: warehouse?.name ?? "" })}</AlertDialogTitle>
          <AlertDialogDescription>
            {holdsStock
              ? t("This warehouse still holds stock. Move it to another warehouse first.")
              : t("The warehouse is empty. Its past movements stay in the items' history.")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <FormAlert message={error} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t("Cancel")}</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy || holdsStock}
            className="bg-destructive text-white hover:bg-destructive/90"
            onClick={async (e) => {
              e.preventDefault();
              if (!warehouse) return;
              setBusy(true);
              try {
                await api(`/warehouses/${warehouse.id}`, { method: "DELETE" });
                onDeleted();
                onClose();
              } catch (err) {
                setError(errorMessage(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("Delete")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
