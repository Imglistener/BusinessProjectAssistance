import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Organization, Project } from "../api/models";
import { STATUS_LABEL } from "../lib/format";
import { useSubmit } from "./AuthLayout";
import { FormAlert, FormField, SimpleSelect, TextField } from "./form";
import { t } from "../i18n";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body: Record<string, string | null> = {
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
        const r = await api<{ project: Project }>(`/organizations/${org!.id}/projects`, { body });
        onSaved(r.project);
      }
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(e instanceof ApiError ? e.message : t("Something went wrong. Try again."));
    },
  );

  const title = editing ? t("Edit project") : t("New project");

  return (
    <form onSubmit={submit} className="grid gap-5" aria-label={title}>
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
          {busy ? t("Saving…") : editing ? t("Save changes") : t("Create project")}
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
