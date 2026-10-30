import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Member, Trip, TripItem, TripItemKind, TripStatus } from "../api/models";
import { AppShell } from "../components/AppShell";
import { Field, FormError, SelectField, useSubmit } from "../components/AuthLayout";
import { TripRoute } from "../components/TripRoute";
import { TripForm } from "../components/TripSection";
import { errorMessage } from "../lib/errors";
import { TRIP_STATUS_LABEL, formatDate, formatDateRange, formatMoney } from "../lib/format";

const KIND_LABEL: Record<TripItemKind, string> = {
  flight: "Flight",
  train: "Train",
  car: "Car",
  hotel: "Hotel",
  meeting: "Meeting",
  other: "Other",
};
const KIND_OPTIONS = Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label }));
const STATUS_OPTIONS = Object.entries(TRIP_STATUS_LABEL).map(([value, label]) => ({ value, label }));

export default function TripDetail() {
  const { projectId, tripId } = useParams();
  const navigate = useNavigate();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(() => {
    api<{ trip: Trip }>(`/trips/${tripId}`)
      .then((r) => setTrip(r.trip))
      .catch((e) =>
        setError(e instanceof ApiError && e.status === 404 ? "We couldn't find that trip." : errorMessage(e)),
      );
  }, [tripId]);

  useEffect(load, [load]);

  const patch = async (body: Record<string, unknown>) => {
    setError(null);
    try {
      const r = await api<{ trip: Trip }>(`/trips/${tripId}`, { method: "PATCH", body });
      setTrip((prev) => (prev ? { ...prev, ...r.trip } : r.trip));
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const remove = async () => {
    try {
      await api(`/trips/${tripId}`, { method: "DELETE" });
      navigate(`/app/projects/${projectId}`, { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <AppShell>
      <Link to={`/app/projects/${projectId}`} className="back no-print">
        {trip?.project_name ?? "Project"}
      </Link>
      <FormError message={error} />
      {!trip && !error && <p className="muted">Loading…</p>}
      {trip && (
        <>
          <header className="main__header">
            <div className="header-actions">
              <h1>{trip.title}</h1>
              <span className="header-links no-print">
                <button type="button" className="link-btn" onClick={() => window.print()}>
                  Print itinerary
                </button>
              </span>
            </div>
            <p className="main__org">
              {trip.destination}. {formatDateRange(trip.start_date, trip.end_date)}
              {trip.nights > 0 ? ` (${trip.nights} ${trip.nights === 1 ? "night" : "nights"})` : " (day trip)"}.
            </p>
            {trip.purpose && <p className="project__description">{trip.purpose}</p>}
          </header>

          {trip.can_edit && !editing && (
            <div className="project-actions no-print">
              <label className="filter">
                <span className="filter__label">Status</span>
                <select value={trip.status} onChange={(e) => patch({ status: e.target.value as TripStatus })}>
                  {STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="btn btn--secondary" onClick={() => setEditing(true)}>
                Edit trip
              </button>
              {confirmDelete ? (
                <span className="row__confirm">
                  <span>Delete it? Linked expenses stay in the project.</span>
                  <button type="button" className="link-btn link-btn--danger" onClick={remove}>
                    Delete trip
                  </button>
                  <button type="button" className="link-btn" onClick={() => setConfirmDelete(false)}>
                    Keep
                  </button>
                </span>
              ) : (
                <button type="button" className="link-btn" onClick={() => setConfirmDelete(true)}>
                  Delete
                </button>
              )}
            </div>
          )}
          {!trip.can_edit && <p className="main__org">Status: {TRIP_STATUS_LABEL[trip.status]}.</p>}

          {editing && (
            <TripForm
              project={{ id: trip.project_id, currency: trip.currency }}
              trip={trip}
              onCancel={() => setEditing(false)}
              onSaved={(t) => {
                setEditing(false);
                setTrip((prev) => (prev ? { ...prev, ...t } : t));
              }}
            />
          )}

          <section className="totals" aria-label="Trip budget">
            <div>
              <span className="totals__label">Budget</span>
              <span className="totals__value">
                {trip.budget ? formatMoney(trip.budget, trip.currency) : "None set"}
              </span>
            </div>
            <div>
              <span className="totals__label">Itinerary estimate</span>
              <span className="totals__value">{formatMoney(trip.estimated_cost, trip.currency)}</span>
            </div>
            <div>
              <span className="totals__label">Spent</span>
              <span className={trip.over_budget ? "totals__value totals__value--over" : "totals__value"}>
                {formatMoney(trip.actual, trip.currency)}
              </span>
            </div>
          </section>

          <TripRoute trip={trip} onSaved={(t) => setTrip((prev) => (prev ? { ...prev, ...t } : t))} />
          <Travelers trip={trip} onSave={(ids) => patch({ traveler_ids: ids })} />
          <Itinerary trip={trip} onChanged={load} />
          <TripExpenses trip={trip} />
        </>
      )}
    </AppShell>
  );
}

function Travelers({ trip, onSave }: { trip: Trip; onSave(ids: number[]): Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [members, setMembers] = useState<Member[]>([]);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [orgId, setOrgId] = useState<number | null>(null);

  useEffect(() => {
    if (!editing) return;
    // The trip doesn't carry its organization; the project does.
    api<{ project: { organization_id: number } }>(`/projects/${trip.project_id}`)
      .then((r) => {
        setOrgId(r.project.organization_id);
        return api<{ members: Member[] }>(`/organizations/${r.project.organization_id}/members`);
      })
      .then((r) => setMembers(r.members))
      .catch(() => setMembers([]));
    setChosen(new Set(trip.travelers.map((t) => t.user_id)));
  }, [editing, trip.project_id, trip.travelers]);

  return (
    <section className="projects-section" aria-labelledby="travelers-heading">
      <div className="section-head">
        <h2 id="travelers-heading">Travelers</h2>
        {trip.can_edit && !editing && (
          <button type="button" className="link-btn no-print" onClick={() => setEditing(true)}>
            Change
          </button>
        )}
      </div>
      {!editing && (
        <p>
          {trip.travelers.length ? (
            trip.travelers.map((t) => t.name).join(", ")
          ) : (
            <span className="muted">Nobody yet.</span>
          )}
        </p>
      )}
      {editing && (
        <div className="panel">
          {orgId === null && <p className="muted">Loading…</p>}
          <div className="travelers">
            {members.map((m) => (
              <label key={m.user_id} className="check">
                <input
                  type="checkbox"
                  checked={chosen.has(m.user_id)}
                  onChange={(e) =>
                    setChosen((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(m.user_id);
                      else next.delete(m.user_id);
                      return next;
                    })
                  }
                />
                {m.name}
              </label>
            ))}
          </div>
          <div className="form__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={async () => {
                await onSave([...chosen]);
                setEditing(false);
              }}
            >
              Save travelers
            </button>
            <button type="button" className="btn btn--quiet" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function Itinerary({ trip, onChanged }: { trip: Trip; onChanged(): void }) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const items = trip.items ?? [];
  const days = [...new Set(items.map((i) => i.date))];

  const remove = async (item: TripItem) => {
    try {
      await api(`/trip-items/${item.id}`, { method: "DELETE" });
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <section className="projects-section" aria-labelledby="itinerary-heading">
      <div className="section-head">
        <h2 id="itinerary-heading">Itinerary</h2>
        {trip.can_edit && !adding && (
          <button type="button" className="btn btn--primary no-print" onClick={() => setAdding(true)}>
            Add to itinerary
          </button>
        )}
      </div>
      <FormError message={error} />
      {adding && (
        <ItemForm
          trip={trip}
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}
      {items.length === 0 && !adding && (
        <p className="muted">Nothing planned yet. Add travel, hotels and meetings day by day.</p>
      )}
      {days.map((d) => (
        <div key={d} className="itinerary__day">
          <h3>{formatDate(d)}</h3>
          <ul className="rows">
            {items
              .filter((i) => i.date === d)
              .map((i) =>
                editingId === i.id ? (
                  <li key={i.id} className="row row--editing">
                    <ItemForm
                      trip={trip}
                      item={i}
                      onCancel={() => setEditingId(null)}
                      onSaved={() => {
                        setEditingId(null);
                        onChanged();
                      }}
                    />
                  </li>
                ) : (
                  <li key={i.id} className="row">
                    <div className="row__main itinerary__item">
                      <span className="itinerary__time">
                        {i.start_time ?? "—"}
                        {i.end_time ? `–${i.end_time}` : ""}
                      </span>
                      <span>
                        <span className="row__title">
                          <span className="tag itinerary__kind">{KIND_LABEL[i.kind]}</span> {i.title}
                        </span>
                        <span className="row__meta">
                          {[i.location, i.confirmation && `Ref. ${i.confirmation}`, i.notes]
                            .filter(Boolean)
                            .join(" — ")}
                        </span>
                      </span>
                    </div>
                    <div className="row__side">
                      {i.estimated_cost && (
                        <span className="row__amount">{formatMoney(i.estimated_cost, trip.currency)}</span>
                      )}
                      {trip.can_edit && (
                        <span className="row__confirm no-print">
                          <button type="button" className="link-btn" onClick={() => setEditingId(i.id)}>
                            Edit
                          </button>
                          <button type="button" className="link-btn" onClick={() => remove(i)}>
                            Remove
                          </button>
                        </span>
                      )}
                    </div>
                  </li>
                ),
              )}
          </ul>
        </div>
      ))}
    </section>
  );
}

function ItemForm({
  trip,
  item,
  onSaved,
  onCancel,
}: {
  trip: Trip;
  item?: TripItem;
  onSaved(): void;
  onCancel(): void;
}) {
  const [form, setForm] = useState({
    kind: item?.kind ?? "meeting",
    title: item?.title ?? "",
    date: item?.date ?? trip.start_date,
    start_time: item?.start_time ?? "",
    end_time: item?.end_time ?? "",
    location: item?.location ?? "",
    confirmation: item?.confirmation ?? "",
    estimated_cost: item?.estimated_cost ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const id = item ? `ti_${item.id}_` : "ti_";

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body = {
        kind: form.kind,
        title: form.title.trim(),
        date: form.date,
        start_time: form.start_time || null,
        end_time: form.end_time || null,
        location: form.location.trim() || null,
        confirmation: form.confirmation.trim() || null,
        estimated_cost: form.estimated_cost.trim() ? form.estimated_cost.trim().replace(",", ".") : null,
      };
      if (item) await api(`/trip-items/${item.id}`, { method: "PATCH", body });
      else await api(`/trips/${trip.id}/items`, { body });
      onSaved();
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label={item ? "Edit itinerary item" : "Add to itinerary"}>
      <h3 className="panel__title">{item ? "Edit itinerary item" : "Add to itinerary"}</h3>
      <FormError message={error} />
      <div className="form__row">
        <SelectField label="Kind" name={`${id}kind`} value={form.kind} onChange={set("kind")} options={KIND_OPTIONS} />
        <Field label="Title" name={`${id}title`} value={form.title} onChange={set("title")} error={fieldErrors.title} />
      </div>
      <div className="form__row form__row--three">
        <Field
          label="Date"
          name={`${id}date`}
          type="date"
          value={form.date}
          onChange={set("date")}
          error={fieldErrors.date}
        />
        <Field
          label="Starts"
          name={`${id}start`}
          type="time"
          value={form.start_time}
          onChange={set("start_time")}
          error={fieldErrors.start_time}
          required={false}
        />
        <Field
          label="Ends"
          name={`${id}end`}
          type="time"
          value={form.end_time}
          onChange={set("end_time")}
          error={fieldErrors.end_time}
          required={false}
        />
      </div>
      <div className="form__row form__row--three">
        <Field
          label="Location"
          name={`${id}location`}
          value={form.location}
          onChange={set("location")}
          required={false}
        />
        <Field
          label="Booking ref."
          name={`${id}ref`}
          value={form.confirmation}
          onChange={set("confirmation")}
          required={false}
        />
        <Field
          label={`Estimated cost (${trip.currency})`}
          name={`${id}cost`}
          value={form.estimated_cost}
          onChange={set("estimated_cost")}
          error={fieldErrors.estimated_cost}
          required={false}
          inputMode="decimal"
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : item ? "Save changes" : "Add"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function TripExpenses({ trip }: { trip: Trip }) {
  const expenses = trip.expenses ?? [];
  return (
    <section className="projects-section" aria-labelledby="trip-expenses-heading">
      <div className="section-head">
        <h2 id="trip-expenses-heading">Expenses</h2>
        <Link to={`/app/projects/${trip.project_id}`} className="no-print">
          Record on the project page
        </Link>
      </div>
      {expenses.length === 0 ? (
        <p className="muted">
          No expenses linked yet. When you record an expense on the project, choose this trip to count it here.
        </p>
      ) : (
        <ul className="rows">
          {expenses.map((e) => (
            <li key={e.id} className={e.status === "valid" ? "row" : "row row--voided"}>
              <div className="row__main">
                <p className="row__title">
                  {e.category}
                  {e.status !== "valid" && <span className="tag">{e.status === "voided" ? "Voided" : "Refunded"}</span>}
                </p>
                <p className="row__meta">
                  {formatDate(e.expense_date)}
                  {e.description ? ` — ${e.description}` : ""}
                </p>
              </div>
              <div className="row__side">
                <span className="row__amount">{formatMoney(e.amount, trip.currency)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
