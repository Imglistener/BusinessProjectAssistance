import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageProjects, type FuelPrice, type Organization, type TravelReference } from "../api/models";
import { useOrg } from "../auth/OrgContext";
import { AppShell } from "../components/AppShell";
import { Field, FormError, SelectField, useSubmit } from "../components/AuthLayout";
import { errorMessage } from "../lib/errors";
import { formatDate, formatMoney, todayIso } from "../lib/format";
import { t } from "../i18n";
import { tx } from "../i18n/rich";

export default function Settings() {
  const { orgs, org, error } = useOrg();
  return (
    <AppShell>
      <header className="main__header">
        <h1>{t("Settings")}</h1>
        {org && <p className="main__org">{org.name}</p>}
      </header>
      <FormError message={error} />
      {orgs === null && !error && <p className="muted">{t("Loading…")}</p>}
      {orgs !== null && !org && (
        <p className="muted">
          {tx("Create your organization on the {dashboard} first.", { dashboard: <Link to="/app">{t("dashboard")}</Link> })}
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
  const [sync, setSync] = useState<PriceList["sync"] | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [synced, setSynced] = useState<string | null>(null);

  type PriceList = {
    prices: FuelPrice[];
    stale_after_days: number;
    sync: { source: string; url: string; license: string; available: boolean };
  };
  const show = (r: PriceList) => {
    setPrices(r.prices);
    setStaleDays(r.stale_after_days);
    setSync(r.sync);
  };

  const load = useCallback(() => {
    api<PriceList>(`/organizations/${org.id}/fuel-prices`)
      .then(show)
      .catch((e) => setError(errorMessage(e, t("Couldn't load fuel prices."))));
  }, [org.id]);

  const updateFromWebsite = async () => {
    setSyncing(true);
    setError(null);
    setSynced(null);
    try {
      const r = await api<PriceList>(`/organizations/${org.id}/fuel-prices/sync`, { method: "POST" });
      show(r);
      setSynced(t("Updated from {source}.", { source: r.sync.source }));
    } catch (e) {
      setError(errorMessage(e, t("Couldn't read the website. Try again later or enter prices by hand.")));
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
        <h2 id="fuel-heading">{t("Fuel prices")}</h2>
        {canEdit && sync?.available && (
          <button type="button" className="btn btn--secondary" onClick={updateFromWebsite} disabled={syncing}>
            {syncing ? t("Updating…") : t("Update from website")}
          </button>
        )}
      </div>
      <p className="muted">
        {t(
          "Pump prices used for trip fuel estimates, per litre in {currency}. A price without a city is used wherever no city price is set. Prices older than {days} days are flagged in estimates, so keep them current.",
          { currency: org.default_currency, days: staleDays },
        )}
      </p>
      {sync?.available && (
        <p className="muted">
          {tx(
            "{button} loads Morocco's national average pump prices from {source} ({license}), updated weekly and then every day by the app. They're averages: the pump price is what counts, so enter a city's own price where you need it.",
            {
              button: <strong>{t("Update from website")}</strong>,
              source: (
                <a href={sync.url} target="_blank" rel="noreferrer">
                  {sync.source}
                </a>
              ),
              license: (
                <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
                  {sync.license}
                </a>
              ),
            },
          )}
        </p>
      )}
      {synced && (
        <p className="notice" role="status">
          {synced}
        </p>
      )}
      <FormError message={error} />
      {prices === null && !error && <p className="muted">{t("Loading…")}</p>}
      {prices && prices.length === 0 && (
        <p className="notice">{t("No prices yet. Add at least a default diesel and petrol price to get fuel estimates.")}</p>
      )}
      {prices && prices.length > 0 && (
        <table className="report__table">
          <thead>
            <tr>
              <th scope="col">{t("City")}</th>
              <th scope="col">{t("Fuel")}</th>
              <th scope="col" className="num">
                {t("Per litre")}
              </th>
              <th scope="col">{t("As of")}</th>
              <th scope="col">{t("Source")}</th>
              {canEdit && <th scope="col" aria-label={t("Actions")} />}
            </tr>
          </thead>
          <tbody>
            {prices.map((p) => (
              <tr key={p.id}>
                <td>{p.city ?? <span className="muted">{t("Any city (default)")}</span>}</td>
                <td>{p.fuel_type === "diesel" ? t("Diesel") : t("Petrol")}</td>
                <td className="num">{formatMoney(p.price_per_litre, p.currency)}</td>
                <td className={p.stale ? "overdue" : undefined}>
                  {formatDate(p.as_of)}
                  {p.stale ? ` (${t("out of date")})` : ""}
                </td>
                <td>{p.source !== "manual" ? t("Website average") : <span className="muted">{t("Entered")}</span>}</td>
                {canEdit && (
                  <td className="num">
                    <button type="button" className="link-btn" onClick={() => remove(p)}>
                      {t("Remove")}
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
    <form onSubmit={submit} className="form price-form" aria-label={t("Add or update a fuel price")}>
      <h3 className="panel__title">{t("Add or update a price")}</h3>
      <FormError message={error} />
      <div className="form__row form__row--four">
        <div className="field">
          <label htmlFor="price_city">{t("City")}</label>
          <div className="field__control">
            <input
              id="price_city"
              list="price-cities"
              placeholder={t("Empty = any city")}
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
          label={t("Fuel")}
          name="price_fuel"
          value={form.fuel_type}
          onChange={set("fuel_type")}
          options={[
            { value: "diesel", label: t("Diesel") },
            { value: "petrol", label: t("Petrol") },
          ]}
        />
        <Field
          label={t("Price per litre ({default_currency})", { default_currency: org.default_currency })}
          name="price_value"
          value={form.price}
          onChange={set("price")}
          error={fieldErrors.price_per_litre}
          inputMode="decimal"
        />
        <Field
          label={t("As of")}
          name="price_as_of"
          type="date"
          value={form.as_of}
          onChange={set("as_of")}
          error={fieldErrors.as_of}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : t("Save price")}
        </button>
      </div>
    </form>
  );
}
