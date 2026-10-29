import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Organization, Project } from "../api/models";
import { Field, FormError, useSubmit } from "./AuthLayout";

interface Props {
  org: Organization;
  onCreated(project: Project): void;
  onCancel(): void;
}

export function ProjectForm({ org, onCreated, onCancel }: Props) {
  const [form, setForm] = useState({
    name: "",
    budget: "",
    currency: org.default_currency,
    start_date: "",
    end_date: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body = {
        name: form.name.trim(),
        budget: form.budget.trim() === "" ? null : form.budget.trim().replace(",", "."),
        currency: form.currency.trim() || null,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      };
      const r = await api<{ project: Project }>(`/organizations/${org.id}/projects`, { body });
      onCreated(r.project);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label="New project">
      <h2 className="panel__title">New project</h2>
      <FormError message={error} />
      <Field label="Project name" name="name" value={form.name} onChange={set("name")} error={fieldErrors.name} />
      <div className="form__row">
        <Field
          label="Budget"
          name="budget"
          value={form.budget}
          onChange={set("budget")}
          error={fieldErrors.budget}
          hint="You can set or change it later."
          required={false}
          inputMode="decimal"
        />
        <Field
          label="Currency"
          name="currency"
          value={form.currency}
          onChange={set("currency")}
          error={fieldErrors.currency}
          hint="Fixed once expenses exist."
          maxLength={3}
        />
      </div>
      <div className="form__row">
        <Field
          label="Start date"
          name="start_date"
          type="date"
          value={form.start_date}
          onChange={set("start_date")}
          error={fieldErrors.start_date}
          required={false}
        />
        <Field
          label="End date"
          name="end_date"
          type="date"
          value={form.end_date}
          onChange={set("end_date")}
          error={fieldErrors.end_date}
          required={false}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create project"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
