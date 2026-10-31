import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageProjects, type FuelPrice, type Organization, type TravelReference } from "../api/models";
import { useOrg } from "../auth/OrgContext";
import { AppShell } from "../components/AppShell";
import { Field, FormError, SelectField, useSubmit } from "../components/AuthLayout";
import { errorMessage } from "../lib/errors";
import { formatDate, formatMoney, todayIso } from "../lib/format";

export default function Settings() {
  const { orgs, org, error } = useOrg();
  return (
    <AppShell>
      <header className="main__header">
        <h1>Settings</h1>
        {org && <p className="main__org">{org.name}</p>}
      </header>
      <FormError message={error} />
      {orgs === null && !error && <p className="muted">Loading…</p>}
      {orgs !== null && !org && (
        <p className="muted">
          Create your organization on the <Link to="/app">dashboard</Link> first.
        </p>
      )}
      {org && <FuelPrices key={org.id} org={org} />}
    </AppShell>
  );
}

function FuelPrices({ org }: { org: Organization }) {
  const canEdit = canManageProjects(org.role);
  const [prices, setPrices] = useState<FuelPrice[] | null>(null);
  const [staleDays, setStaleDays] = useState(30);
  const [cities, setCities] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sync, setSync] = useState<{ source: string; url: string; available: boolean } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [synced, setSynced] = useState<string | null>(null);

  type PriceList = {
    prices: FuelPrice[];
    stale_after_days: number;
    sync: { source: string; url: string; available: boolean };
  };
  const show = (r: PriceList) => {
    setPrices(r.prices);
    setStaleDays(r.stale_after_days);
    setSync(r.sync);
  };

  const load = useCallback(() => {
    api<PriceList>(`/organizations/${org.id}/fuel-prices`)
      .then(show)
      .catch((e) => setError(errorMessage(e, "Couldn't load fuel prices.")));
  }, [org.id]);

  const updateFromWebsite = async () => {
    setSyncing(true);
    setError(null);
    setSynced(null);
    try {
      const r = await api<PriceList>(`/organizations/${org.id}/fuel-prices/sync`, { method: "POST" });
      show(r);
      setSynced(`Updated from ${r.sync.source}.`);
    } catch (e) {
      setError(errorMessage(e, "Couldn't read the website. Try again later or enter prices by hand."));
    } finally {
      setSyncing(false);
    }
  };

  useEffect(load, [load]);
  useEffect(() => {
    api<TravelReference>("/travel/reference")
      .then((r) => setCities(r.cities.map((c) => c.name)))
      .catch(() => setCities([]));
  }, []);

  const remove = async (p: FuelPrice) => {
    try {
      await api(`/fuel-prices/${p.id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <section className="card" aria-labelledby="fuel-heading">
      <div className="section-head">
        <h2 id="fuel-heading">Fuel prices</h2>
        {canEdit && sync?.available && (
          <button type="button" className="btn btn--secondary" onClick={updateFromWebsite} disabled={syncing}>
            {syncing ? "Updating…" : "Update from website"}
          </button>
        )}
      </div>
      <p className="muted">
        Pump prices used for trip fuel estimates, per litre in {org.default_currency}. A price without a city is used
        wherever no city price is set. Prices older than {staleDays} days are flagged in estimates, so keep them
        current.
      </p>
      {sync?.available && (
        <p className="muted">
          <strong>Update from website</strong> loads today's average prices (national and main cities) from{" "}
          <a href={sync.url} target="_blank" rel="noreferrer">
            {sync.source}
          </a>
          , a community price service. They're averages: the pump price is what counts.
        </p>
      )}
      {synced && (
        <p className="notice" role="status">
          {synced}
        </p>
      )}
      <FormError message={error} />
      {prices === null && !error && <p className="muted">Loading…</p>}
      {prices && prices.length === 0 && (
        <p className="notice">No prices yet. Add at least a default diesel and petrol price to get fuel estimates.</p>
      )}
      {prices && prices.length > 0 && (
        <table className="report__table">
          <thead>
            <tr>
              <th scope="col">City</th>
              <th scope="col">Fuel</th>
              <th scope="col" className="num">
                Per litre
              </th>
              <th scope="col">As of</th>
              <th scope="col">Source</th>
              {canEdit && <th scope="col" aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {prices.map((p) => (
              <tr key={p.id}>
                <td>{p.city ?? <span className="muted">Any city (default)</span>}</td>
                <td>{p.fuel_type === "diesel" ? "Diesel" : "Petrol"}</td>
                <td className="num">{formatMoney(p.price_per_litre, p.currency)}</td>
                <td className={p.stale ? "overdue" : undefined}>
                  {formatDate(p.as_of)}
                  {p.stale ? " (out of date)" : ""}
                </td>
                <td>{p.source === "teraedge" ? "Website average" : <span className="muted">Entered</span>}</td>
                {canEdit && (
                  <td className="num">
                    <button type="button" className="link-btn" onClick={() => remove(p)}>
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && <PriceForm org={org} cities={cities} onSaved={load} />}
    </section>
  );
}

function PriceForm({ org, cities, onSaved }: { org: Organization; cities: string[]; onSaved(): void }) {
  const [form, setForm] = useState({ city: "", fuel_type: "diesel", price: "", as_of: todayIso() });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      await api(`/organizations/${org.id}/fuel-prices`, {
        method: "PUT",
        body: {
          city: form.city.trim() || null,
          fuel_type: form.fuel_type,
          price_per_litre: form.price.trim().replace(",", "."),
          as_of: form.as_of,
        },
      });
      setForm((f) => ({ ...f, price: "" }));
      onSaved();
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="form price-form" aria-label="Add or update a fuel price">
      <h3 className="panel__title">Add or update a price</h3>
      <FormError message={error} />
      <div className="form__row form__row--four">
        <div className="field">
          <label htmlFor="price_city">City</label>
          <div className="field__control">
            <input
              id="price_city"
              list="price-cities"
              placeholder="Empty = any city"
              value={form.city}
              onChange={(e) => set("city")(e.target.value)}
            />
          </div>
          <datalist id="price-cities">
            {cities.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
        <SelectField
          label="Fuel"
          name="price_fuel"
          value={form.fuel_type}
          onChange={set("fuel_type")}
          options={[
            { value: "diesel", label: "Diesel" },
            { value: "petrol", label: "Petrol" },
          ]}
        />
        <Field
          label={`Price per litre (${org.default_currency})`}
          name="price_value"
          value={form.price}
          onChange={set("price")}
          error={fieldErrors.price_per_litre}
          inputMode="decimal"
        />
        <Field
          label="As of"
          name="price_as_of"
          type="date"
          value={form.as_of}
          onChange={set("as_of")}
          error={fieldErrors.as_of}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save price"}
        </button>
      </div>
    </form>
  );
}
