import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canContribute, type Project, type Trip } from "../api/models";
import { errorMessage } from "../lib/errors";
import { TRIP_STATUS_LABEL, formatDateRange, formatMoney } from "../lib/format";
import { Field, FormError, useSubmit } from "./AuthLayout";
import { t } from "../i18n";

/** Trips on the project page. Each links to its own page with the itinerary. */
export function TripSection({ project, onTripsChange }: { project: Project; onTripsChange?(trips: Trip[]): void }) {
  const editable = project.status !== "archived" && canContribute(project.my_role ?? "viewer");
  const [trips, setTrips] = useState<Trip[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ trips: Trip[] }>(`/projects/${project.id}/trips`)
      .then((r) => {
        setTrips(r.trips);
        onTripsChange?.(r.trips);
      })
      .catch((e) => setError(errorMessage(e, t("Couldn't load trips."))));
    // Reload per project only; onTripsChange is just a notification.
  }, [project.id]);

  if (!editable && trips !== null && trips.length === 0) return null;

  return (
    <section className="projects-section" aria-labelledby="trips-heading">
      <div className="section-head">
        <h2 id="trips-heading">{t("Trips")}</h2>
        {editable && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            {t("Plan a trip")}
          </button>
        )}
      </div>
      <FormError message={error} />
      {adding && (
        <TripForm
          project={project}
          onCancel={() => setAdding(false)}
          onSaved={(x) => {
            setAdding(false);
            const next = [...(trips ?? []), x].sort((a, b) => a.start_date.localeCompare(b.start_date));
            setTrips(next);
            onTripsChange?.(next);
          }}
        />
      )}
      {trips === null && !error && <p className="muted">{t("Loading…")}</p>}
      {trips && trips.length === 0 && !adding && (
        <p className="muted">{t("No trips yet. Plan travel for this project: itinerary, travelers and budget.")}</p>
      )}
      {trips && trips.length > 0 && (
        <ul className="rows">
          {trips.map((x) => (
            <li key={x.id} className={x.status === "cancelled" ? "row row--voided" : "row"}>
              <div className="row__main">
                <p className="row__title">
                  <Link to={`/app/projects/${project.id}/trips/${x.id}`} className="trip__link">
                    {x.title}
                  </Link>
                  <span className="tag">{TRIP_STATUS_LABEL[x.status]}</span>
                  {x.over_budget && <span className="tag tag--warn">{t("Over budget")}</span>}
                </p>
                <p className="row__meta">
                  {x.destination} — {formatDateRange(x.start_date, x.end_date)}
                  {x.travelers.length > 0 && ` — ${x.travelers.map((x) => x.name.split(" ")[0]).join(t(", "))}`}
                </p>
              </div>
              <div className="row__side">
                <span className="row__amount">
                  {formatMoney(x.actual, x.currency)}
                  <small className="inventory__value">
                    {x.budget ? t("of {amount}", { amount: formatMoney(x.budget, x.currency) }) : t("no budget")}
                  </small>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function TripForm({
  project,
  trip,
  onSaved,
  onCancel,
}: {
  project: { id: number; currency: string };
  trip?: Trip;
  onSaved(trip: Trip): void;
  onCancel(): void;
}) {
  const [form, setForm] = useState({
    title: trip?.title ?? "",
    destination: trip?.destination ?? "",
    start_date: trip?.start_date ?? "",
    end_date: trip?.end_date ?? "",
    budget: trip?.budget ?? "",
    purpose: trip?.purpose ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const id = trip ? `trip_${trip.id}_` : "trip_";

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body = {
        title: form.title.trim(),
        destination: form.destination.trim(),
        start_date: form.start_date,
        end_date: form.end_date || form.start_date,
        budget: form.budget.trim() ? form.budget.trim().replace(",", ".") : null,
        purpose: form.purpose.trim() || null,
      };
      const r = trip
        ? await api<{ trip: Trip }>(`/trips/${trip.id}`, { method: "PATCH", body })
        : await api<{ trip: Trip }>(`/projects/${project.id}/trips`, { body });
      onSaved(r.trip);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label={trip ? t("Edit trip") : t("Plan a trip")}>
      <h3 className="panel__title">{trip ? t("Edit trip") : t("Plan a trip")}</h3>
      <FormError message={error} />
      <div className="form__row">
        <Field label={t("Title")} name={`${id}title`} value={form.title} onChange={set("title")} error={fieldErrors.title} />
        <Field
          label={t("Destination")}
          name={`${id}destination`}
          value={form.destination}
          onChange={set("destination")}
          error={fieldErrors.destination}
        />
      </div>
      <div className="form__row">
        <Field
          label={t("From")}
          name={`${id}start`}
          type="date"
          value={form.start_date}
          onChange={set("start_date")}
          error={fieldErrors.start_date}
        />
        <Field
          label={t("To")}
          name={`${id}end`}
          type="date"
          value={form.end_date}
          onChange={set("end_date")}
          error={fieldErrors.end_date}
          required={false}
          hint={t("Leave empty for a day trip.")}
        />
      </div>
      <div className="form__row">
        <Field
          label={t("Budget ({currency})", { currency: project.currency })}
          name={`${id}budget`}
          value={form.budget}
          onChange={set("budget")}
          error={fieldErrors.budget}
          required={false}
          inputMode="decimal"
        />
        <Field
          label={t("Purpose")}
          name={`${id}purpose`}
          value={form.purpose}
          onChange={set("purpose")}
          error={fieldErrors.purpose}
          required={false}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : trip ? t("Save changes") : t("Create trip")}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
