import { Plus, X } from "lucide-react";
import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Organization, Project } from "../api/models";
import { STATUS_LABEL } from "../lib/format";
import { useSubmit } from "./AuthLayout";
import { FormAlert, FormField, SimpleSelect, TextField } from "./form";
import { t } from "../i18n";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

// Archiving has its own button (with a confirmation), so it isn't offered here.
const STATUS_OPTIONS = ["planned", "active", "on_hold", "completed"].map((s) => ({ value: s, label: STATUS_LABEL[s] }));

interface Props {
  org?: Organization;
  /** Edit this project instead of creating one in `org`. */
  project?: Project;
  onSaved(project: Project): void;
  onCancel(): void;
}

export function ProjectForm({ org, project, onSaved, onCancel }: Props) {
  const editing = project !== undefined;
  const initial = {
    name: project?.name ?? "",
    description: project?.description ?? "",
    status: project && project.status !== "archived" ? project.status : "planned",
    budget: project && Number(project.budget) > 0 ? project.budget : "",
    currency: project?.currency ?? org?.default_currency ?? "MAD",
    start_date: project?.start_date ?? "",
    end_date: project?.end_date ?? "",
  };
  const [form, setForm] = useState(initial);
  // Creating has an optional second step: the project's opening inventory.
  const [step, setStep] = useState<1 | 2>(1);
  const [stock, setStock] = useState<OpeningRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      if (!editing && step === 1) {
        setStep(2);
        return;
      }
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        budget: form.budget.trim() === "" ? (editing ? "0" : null) : form.budget.trim().replace(",", "."),
        currency: form.currency.trim() || null,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      };
      if (editing) {
        // An archived project keeps its status here; "Restore" changes it.
        if (project.status !== "archived") body.status = form.status;
        const r = await api<{ project: Project }>(`/projects/${project.id}`, { method: "PATCH", body });
        onSaved(r.project);
      } else {
        body.status = form.status;
        body.inventory = openingInventory(stock);
        const r = await api<{ project: Project }>(`/organizations/${org!.id}/projects`, { body });
        onSaved(r.project);
      }
    },
    (e) => {
      if (e instanceof ApiError && e.field === "inventory") setError(e.message);
      else if (e instanceof ApiError && e.field) {
        setFieldErrors({ [e.field]: e.message });
        setStep(1); // the problem is with the project's details
      } else setError(e instanceof ApiError ? e.message : t("Something went wrong. Try again."));
    },
  );

  const title = editing ? t("Edit project") : t("New project");

  if (!editing && step === 2) {
    return (
      <form onSubmit={submit} className="grid gap-5" aria-label={title}>
        <div className="grid gap-1">
          <p className="text-sm font-medium">{t("Opening inventory (optional)")}</p>
          <p className="text-xs text-muted-foreground">
            {t("List what this project starts with. You can add warehouses and more stock later, or ask the assistant.")}
          </p>
        </div>
        <FormAlert message={error} />
        <OpeningInventoryEditor rows={stock} onChange={setStock} currency={form.currency || "MAD"} />
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={() => setStep(1)}>
            {t("Back")}
          </Button>
          <div className="flex gap-2">
            {stock.every((r) => !r.name.trim()) ? (
              <Button type="submit" disabled={busy}>
                {busy ? t("Saving…") : t("Skip and create project")}
              </Button>
            ) : (
              <Button type="submit" disabled={busy}>
                {busy ? t("Saving…") : t("Create project")}
              </Button>
            )}
          </div>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-5" aria-label={title}>
      {!editing && <StepHint />}
      <FormAlert message={error} />
      <TextField
        id="name"
        label={t("Project name")}
        value={form.name}
        onChange={(e) => set("name")(e.target.value)}
        error={fieldErrors.name}
        required
        maxLength={200}
        autoFocus
      />
      <FormField id="description" label={t("Description")} error={fieldErrors.description}>
        <Textarea
          id="description"
          name="description"
          rows={3}
          maxLength={5000}
          value={form.description}
          onChange={(e) => set("description")(e.target.value)}
        />
      </FormField>
      <div className="grid gap-5 sm:grid-cols-[1fr_8rem]">
        <TextField
          id="budget"
          label={t("Budget")}
          value={form.budget}
          onChange={(e) => set("budget")(e.target.value)}
          error={fieldErrors.budget}
          hint={editing ? t("Leave empty for no budget.") : t("You can set or change it later.")}
          inputMode="decimal"
          className="tabular"
        />
        <TextField
          id="currency"
          label={t("Currency")}
          value={form.currency}
          onChange={(e) => set("currency")(e.target.value.toUpperCase())}
          error={fieldErrors.currency}
          hint={t("Fixed once expenses exist.")}
          maxLength={3}
          required
        />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField
          id="start_date"
          type="date"
          label={t("Start date")}
          value={form.start_date}
          onChange={(e) => set("start_date")(e.target.value)}
          error={fieldErrors.start_date}
        />
        <TextField
          id="end_date"
          type="date"
          label={t("End date")}
          value={form.end_date}
          onChange={(e) => set("end_date")(e.target.value)}
          error={fieldErrors.end_date}
        />
      </div>
      {!(editing && project.status === "archived") && (
        <FormField id="status" label={t("Status")}>
          <SimpleSelect id="status" value={form.status} onChange={set("status")} options={STATUS_OPTIONS} />
        </FormField>
      )}
      <div className="flex flex-wrap justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("Cancel")}
        </Button>
        <Button type="submit" disabled={busy}>
          {busy ? t("Saving…") : editing ? t("Save changes") : t("Continue")}
        </Button>
      </div>
    </form>
  );
}

/** The project form in a dialog (dashboard "New project", project page "Edit project"). */
export function ProjectFormDialog({
  open,
  onOpenChange,
  ...props
}: Omit<Props, "onCancel"> & { open: boolean; onOpenChange(open: boolean): void }) {
  const editing = props.project !== undefined;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? t("Edit project") : t("New project")}</DialogTitle>
          <DialogDescription>
            {editing ? t("Changes are recorded in the project's activity.") : t("Add a budget and dates now or later.")}
          </DialogDescription>
        </DialogHeader>
        {open && <ProjectForm {...props} onCancel={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

/** "Step 1 of 2" for a new project; the second step (opening inventory) is optional. */
function StepHint() {
  return (
    <ol className="flex items-center gap-2 text-xs text-muted-foreground" aria-label={t("Steps")}>
      <li className="rounded-full bg-primary px-2 py-0.5 font-medium text-primary-foreground">{t("1. Details")}</li>
      <li aria-hidden="true">—</li>
      <li className="rounded-full border px-2 py-0.5">{t("2. Inventory (optional)")}</li>
    </ol>
  );
}

interface OpeningRow {
  name: string;
  unit: string;
  quantity: string;
  unit_cost: string;
}

const blank = (): OpeningRow => ({ name: "", unit: "pcs", quantity: "", unit_cost: "" });

function openingInventory(rows: OpeningRow[]) {
  const n = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));
  return rows
    .filter((r) => r.name.trim())
    .map((r) => ({ name: r.name.trim(), unit: r.unit.trim() || "pcs", quantity: n(r.quantity), unit_cost: n(r.unit_cost) }));
}

/** Rows of name, unit, quantity and unit cost, for a new project's starting stock. */
function OpeningInventoryEditor({ rows, onChange, currency }: { rows: OpeningRow[]; onChange(rows: OpeningRow[]): void; currency: string }) {
  const list = rows.length ? rows : [blank()];
  const update = (i: number, key: keyof OpeningRow, value: string) =>
    onChange(list.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  return (
    <div className="grid gap-2">
      <div className="hidden grid-cols-[minmax(0,1fr)_5rem_5.5rem_6.5rem_2rem] gap-2 px-1 text-xs text-muted-foreground sm:grid">
        <span>{t("Item")}</span>
        <span>{t("Unit")}</span>
        <span>{t("Quantity")}</span>
        <span>{t("Unit cost ({default_currency})", { default_currency: currency })}</span>
      </div>
      {list.map((r, i) => (
        <div key={i} className="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_5rem_5.5rem_6.5rem_2rem]">
          <Input className="col-span-2 sm:col-span-1" value={r.name} onChange={(e) => update(i, "name", e.target.value)}
            placeholder={t("e.g. Folding chairs")} aria-label={t("Item")} maxLength={200} autoFocus={i === list.length - 1 && i > 0} />
          <Input value={r.unit} onChange={(e) => update(i, "unit", e.target.value)} aria-label={t("Unit")} maxLength={20} />
          <Input className="tabular" value={r.quantity} inputMode="decimal" onChange={(e) => update(i, "quantity", e.target.value)}
            aria-label={t("Quantity")} placeholder="0" />
          <Input className="tabular" value={r.unit_cost} inputMode="decimal" onChange={(e) => update(i, "unit_cost", e.target.value)}
            aria-label={t("Unit cost ({default_currency})", { default_currency: currency })} />
          <Button type="button" variant="ghost" size="icon" className="size-9" aria-label={t("Remove")}
            onClick={() => onChange(list.filter((_, j) => j !== i))} disabled={list.length === 1 && !r.name}>
            <X className="size-4" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => onChange([...list, blank()])}>
        <Plus className="size-4" />
        {t("Add a line")}
      </Button>
    </div>
  );
}
