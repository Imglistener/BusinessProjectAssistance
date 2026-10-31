import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Organization, Project } from "../api/models";
import { STATUS_LABEL } from "../lib/format";
import { Field, FormError, SelectField, useSubmit } from "./AuthLayout";
import { t } from "../i18n";

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
    <form onSubmit={submit} className="panel form" aria-label={title}>
      <h2 className="panel__title">{title}</h2>
      <FormError message={error} />
      <Field label={t("Project name")} name="name" value={form.name} onChange={set("name")} error={fieldErrors.name} />
      <div className="field">
        <label htmlFor="description">{t("Description")}</label>
        <div className="field__control">
          <textarea
            id="description"
            name="description"
            rows={3}
            maxLength={5000}
            value={form.description}
            onChange={(e) => set("description")(e.target.value)}
          />
        </div>
        {fieldErrors.description && <p className="field__message field__message--error">{fieldErrors.description}</p>}
      </div>
      <div className="form__row">
        <Field
          label={t("Budget")}
          name="budget"
          value={form.budget}
          onChange={set("budget")}
          error={fieldErrors.budget}
          hint={editing ? t("Leave empty for no budget.") : t("You can set or change it later.")}
          required={false}
          inputMode="decimal"
        />
        <Field
          label={t("Currency")}
          name="currency"
          value={form.currency}
          onChange={set("currency")}
          error={fieldErrors.currency}
          hint={t("Fixed once expenses exist.")}
          maxLength={3}
        />
      </div>
      <div className="form__row">
        <Field
          label={t("Start date")}
          name="start_date"
          type="date"
          value={form.start_date}
          onChange={set("start_date")}
          error={fieldErrors.start_date}
          required={false}
        />
        <Field
          label={t("End date")}
          name="end_date"
          type="date"
          value={form.end_date}
          onChange={set("end_date")}
          error={fieldErrors.end_date}
          required={false}
        />
      </div>
      {!(editing && project.status === "archived") && (
        <SelectField label={t("Status")} name="status" value={form.status} onChange={set("status")} options={STATUS_OPTIONS} />
      )}
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : editing ? t("Save changes") : t("Create project")}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
