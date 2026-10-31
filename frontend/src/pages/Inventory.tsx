import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import {
  canContribute,
  canManageProjects,
  type InventoryItem,
  type InventorySummary,
  type Movement,
  type Organization,
  type Project,
} from "../api/models";
import { useOrg } from "../auth/OrgContext";
import { AppShell } from "../components/AppShell";
import { Field, FormError, SelectField, useSubmit } from "../components/AuthLayout";
import { FilterBar, FilterCheck, useDebounced } from "../components/Filters";
import { formatWhen } from "../lib/activity";
import { errorMessage } from "../lib/errors";
import { formatMoney, formatNumber } from "../lib/format";
import { AnimatedMoney } from "../components/AnimatedMoney";
import { t } from "../i18n";
import { tx } from "../i18n/rich";

const qty = (q: string, unit: string) => `${formatNumber(q)} ${unit}`;
const KIND_LABEL: Record<string, string> = {
  receive: t("Received"),
  issue: t("Issued"),
  adjust: t("Adjusted"),
  count: t("Counted"),
};

export default function Inventory() {
  const { orgs, org, error } = useOrg();
  return (
    <AppShell>
      <header className="main__header">
        <h1>{t("Inventory")}</h1>
        {org && (
          <p className="main__org">
            {t("Stock kept by {organization}. Values in {currency}.", { organization: org.name, currency: org.default_currency })}
          </p>
        )}
      </header>
      <FormError message={error} />
      {orgs === null && !error && <p className="muted">{t("Loading…")}</p>}
      {orgs !== null && !org && (
        <p className="muted">
          {tx("Create your organization on the {dashboard} first.", { dashboard: <Link to="/app">{t("dashboard")}</Link> })}
        </p>
      )}
      {org && <InventoryManager key={org.id} org={org} />}
    </AppShell>
  );
}

function InventoryManager({ org }: { org: Organization }) {
  const canManage = canManageProjects(org.role);
  const canMove = canContribute(org.role);
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [mode, setMode] = useState<"list" | "add" | "count">("list");
  const q = useDebounced(search.trim());

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (lowOnly) params.set("low_stock", "true");
  if (showArchived) params.set("include_archived", "true");
  const query = params.toString();

  const load = useCallback(() => {
    api<{ items: InventoryItem[]; summary: InventorySummary }>(`/organizations/${org.id}/inventory?${query}`)
      .then((r) => {
        setError(null);
        setItems(r.items);
        setSummary(r.summary);
      })
      .catch((e) => setError(errorMessage(e, t("Couldn't load the inventory."))));
  }, [org.id, query]);

  useEffect(load, [load]);
  useEffect(() => {
    api<{ projects: Project[] }>(`/organizations/${org.id}/projects`)
      .then((r) => setProjects(r.projects))
      .catch(() => setProjects([]));
  }, [org.id]);

  const replace = (item: InventoryItem) => {
    setItems((prev) => prev?.map((i) => (i.id === item.id ? item : i)) ?? prev);
    // Totals and low-stock counts move with every change; refresh them.
    load();
  };

  if (mode === "count" && items) {
    return (
      <StockCount
        org={org}
        onDone={() => {
          setMode("list");
          load();
        }}
      />
    );
  }

  return (
    <>
      {summary && (
        <section className="totals" aria-label={t("Inventory totals")}>
          <div>
            <span className="totals__label">{t("Items in stock")}</span>
            <span className="totals__value">{summary.item_count}</span>
          </div>
          <div>
            <span className="totals__label">{t("Stock value")}</span>
            <AnimatedMoney className="totals__value" amount={summary.stock_value} currency={summary.currency} />
          </div>
          <div>
            <span className="totals__label">{t("Low stock")}</span>
            <span className={summary.low_stock_count > 0 ? "totals__value totals__value--over" : "totals__value"}>
              {summary.low_stock_count}
            </span>
          </div>
        </section>
      )}
      {summary && summary.unpriced_item_count > 0 && (
        <p className="muted inventory__note">
          {t("{count} items have no unit cost, so they aren't in the stock value.", { count: summary.unpriced_item_count })}
        </p>
      )}

      <FormError message={error} />

      <section className="projects-section" aria-labelledby="items-heading">
        <div className="section-head">
          <h2 id="items-heading">{t("Items")}</h2>
          <div className="form__actions">
            {canMove && items && items.length > 0 && mode === "list" && (
              <button type="button" className="btn btn--secondary" onClick={() => setMode("count")}>
                {t("Stock count")}
              </button>
            )}
            {canManage && mode === "list" && (
              <button type="button" className="btn btn--primary" onClick={() => setMode("add")}>
                {t("Add item")}
              </button>
            )}
          </div>
        </div>

        {mode === "add" && (
          <ItemForm
            org={org}
            onCancel={() => setMode("list")}
            onSaved={() => {
              setMode("list");
              load();
            }}
          />
        )}

        <FilterBar label={t("Filter items")}>
          <label className="filter filter--grow">
            <span className="filter__label">{t("Search")}</span>
            <input
              type="search"
              placeholder={t("Name, SKU or location")}
              value={search}
              maxLength={100}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <FilterCheck label={t("Only low stock")} checked={lowOnly} onChange={setLowOnly} />
          <FilterCheck label={t("Show archived")} checked={showArchived} onChange={setShowArchived} />
        </FilterBar>

        {items === null && !error && <p className="muted">{t("Loading…")}</p>}
        {items && items.length === 0 && (
          <p className="muted">
            {q || lowOnly
              ? t("No items match these filters.")
              : canManage
                ? t("No items yet. Add what you keep in stock, with a reorder level to get low-stock warnings.")
                : t("No items yet.")}
          </p>
        )}
        {items && items.length > 0 && (
          <ul className="rows">
            {items.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                org={org}
                projects={projects}
                canManage={canManage}
                canMove={canMove}
                onChange={replace}
                onError={setError}
              />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function ItemRow({
  item,
  org,
  projects,
  canManage,
  canMove,
  onChange,
  onError,
}: {
  item: InventoryItem;
  org: Organization;
  projects: Project[];
  canManage: boolean;
  canMove: boolean;
  onChange(item: InventoryItem): void;
  onError(message: string): void;
}) {
  const [panel, setPanel] = useState<null | "receive" | "issue" | "adjust" | "edit" | "history">(null);
  const meta = [item.sku, item.location].filter(Boolean).join(" — ");

  const toggleArchive = async () => {
    try {
      const r = await api<{ item: InventoryItem }>(`/inventory/${item.id}`, {
        method: "PATCH",
        body: { archived: !item.archived },
      });
      onChange(r.item);
    } catch (e) {
      onError(errorMessage(e));
    }
  };

  return (
    <li className={item.archived ? "row row--voided row--stacked" : "row row--stacked"}>
      <div className="row row--plain">
        <div className="row__main">
          <p className="row__title">
            {item.name}
            {item.low_stock && <span className="tag tag--warn">{t("Low stock")}</span>}
            {item.archived && <span className="tag">{t("Archived")}</span>}
          </p>
          <p className="row__meta">
            {meta ? `${meta} — ` : ""}
            {item.unit_cost ? t("{price} per {unit}", { price: formatMoney(item.unit_cost, item.currency), unit: item.unit }) : t("No unit cost")}
            {item.reorder_level ? ` — ${t("reorder at {quantity}", { quantity: qty(item.reorder_level, item.unit) })}` : ""}
          </p>
        </div>
        <div className="row__side">
          <span className="row__amount">
            {qty(item.quantity_on_hand, item.unit)}
            {item.stock_value && (
              <small className="inventory__value">{formatMoney(item.stock_value, item.currency)}</small>
            )}
          </span>
        </div>
      </div>
      <div className="row__confirm inventory__actions">
        {!item.archived && canMove && (
          <>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "receive" ? null : "receive")}>
              {t("Receive")}
            </button>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "issue" ? null : "issue")}>
              {t("Issue")}
            </button>
          </>
        )}
        {!item.archived && canManage && (
          <>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "adjust" ? null : "adjust")}>
              {t("Adjust")}
            </button>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "edit" ? null : "edit")}>
              {t("Edit")}
            </button>
          </>
        )}
        <button type="button" className="link-btn" onClick={() => setPanel(panel === "history" ? null : "history")}>
          {t("History")}
        </button>
        {canManage && (
          <button type="button" className="link-btn" onClick={toggleArchive}>
            {item.archived ? t("Restore") : t("Archive")}
          </button>
        )}
      </div>

      {(panel === "receive" || panel === "issue" || panel === "adjust") && (
        <MovementForm
          item={item}
          kind={panel}
          projects={projects}
          onCancel={() => setPanel(null)}
          onSaved={(updated) => {
            setPanel(null);
            onChange(updated);
          }}
        />
      )}
      {panel === "edit" && (
        <ItemForm
          org={org}
          item={item}
          onCancel={() => setPanel(null)}
          onSaved={(updated) => {
            setPanel(null);
            onChange(updated);
          }}
        />
      )}
      {panel === "history" && <History item={item} />}
    </li>
  );
}

function MovementForm({
  item,
  kind,
  projects,
  onSaved,
  onCancel,
}: {
  item: InventoryItem;
  kind: "receive" | "issue" | "adjust";
  projects: Project[];
  onSaved(item: InventoryItem): void;
  onCancel(): void;
}) {
  const [quantity, setQuantity] = useState("");
  const [projectId, setProjectId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const id = `move_${item.id}_`;
  const title = { receive: t("Receive stock"), issue: t("Issue stock"), adjust: t("Adjust stock") }[kind];

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const r = await api<{ item: InventoryItem }>(`/inventory/${item.id}/movements`, {
        body: {
          kind,
          quantity: quantity.trim().replace(",", "."),
          note: note.trim() || null,
          project_id: kind === "issue" && projectId ? Number(projectId) : null,
        },
      });
      onSaved(r.item);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form inventory__form" aria-label={`${title}: ${item.name}`}>
      <h3 className="panel__title">{title}</h3>
      <FormError message={error} />
      <div className="form__row">
        <Field
          label={kind === "adjust" ? t("Change ({unit}, use - to remove)", { unit: item.unit }) : t("Quantity ({unit})", { unit: item.unit })}
          name={`${id}qty`}
          value={quantity}
          onChange={setQuantity}
          error={fieldErrors.quantity}
          inputMode="decimal"
        />
        {kind === "issue" ? (
          <SelectField
            label={t("For project")}
            name={`${id}project`}
            value={projectId}
            onChange={setProjectId}
            options={[
              { value: "", label: t("No project") },
              ...projects.map((p) => ({ value: String(p.id), label: p.name })),
            ]}
          />
        ) : (
          <Field
            label={kind === "adjust" ? t("Reason") : t("Note")}
            name={`${id}note`}
            value={note}
            onChange={setNote}
            error={fieldErrors.note}
            required={kind === "adjust"}
          />
        )}
      </div>
      {kind === "issue" && (
        <Field
          label={t("Note")}
          name={`${id}note`}
          value={note}
          onChange={setNote}
          error={fieldErrors.note}
          required={false}
        />
      )}
      {fieldErrors.project_id && <p className="field__message field__message--error">{fieldErrors.project_id}</p>}
      <p className="muted">{t("On hand now: {quantity}.", { quantity: qty(item.quantity_on_hand, item.unit) })}</p>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : title}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}

function ItemForm({
  org,
  item,
  onSaved,
  onCancel,
}: {
  org: Organization;
  item?: InventoryItem;
  onSaved(item: InventoryItem): void;
  onCancel(): void;
}) {
  const [form, setForm] = useState({
    name: item?.name ?? "",
    sku: item?.sku ?? "",
    unit: item?.unit ?? "pcs",
    unit_cost: item?.unit_cost ?? "",
    reorder_level: item?.reorder_level ?? "",
    location: item?.location ?? "",
    quantity: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const id = item ? `item_${item.id}_` : "item_";
  const num = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body: Record<string, string | null> = {
        name: form.name.trim(),
        sku: form.sku.trim() || null,
        unit: form.unit.trim() || "pcs",
        unit_cost: num(form.unit_cost),
        reorder_level: num(form.reorder_level),
        location: form.location.trim() || null,
      };
      const r = item
        ? await api<{ item: InventoryItem }>(`/inventory/${item.id}`, { method: "PATCH", body })
        : await api<{ item: InventoryItem }>(`/organizations/${org.id}/inventory`, {
            body: { ...body, quantity: num(form.quantity) },
          });
      onSaved(r.item);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form inventory__form" aria-label={item ? t("Edit item") : t("Add item")}>
      <h3 className="panel__title">{item ? t("Edit item") : t("Add item")}</h3>
      <FormError message={error} />
      <div className="form__row">
        <Field label={t("Name")} name={`${id}name`} value={form.name} onChange={set("name")} error={fieldErrors.name} />
        <Field
          label={t("SKU")}
          name={`${id}sku`}
          value={form.sku}
          onChange={set("sku")}
          error={fieldErrors.sku}
          required={false}
        />
      </div>
      <div className="form__row">
        <Field
          label={t("Unit")}
          name={`${id}unit`}
          value={form.unit}
          onChange={set("unit")}
          error={fieldErrors.unit}
          hint={t("pcs, box, kg, litre…")}
          maxLength={20}
        />
        <Field
          label={t("Unit cost ({default_currency})", { default_currency: org.default_currency })}
          name={`${id}cost`}
          value={form.unit_cost}
          onChange={set("unit_cost")}
          error={fieldErrors.unit_cost}
          required={false}
          inputMode="decimal"
        />
      </div>
      <div className="form__row">
        <Field
          label={t("Reorder level")}
          name={`${id}reorder`}
          value={form.reorder_level}
          onChange={set("reorder_level")}
          error={fieldErrors.reorder_level}
          hint={t("Warn when stock gets this low.")}
          required={false}
          inputMode="decimal"
        />
        <Field
          label={t("Location")}
          name={`${id}location`}
          value={form.location}
          onChange={set("location")}
          error={fieldErrors.location}
          required={false}
        />
      </div>
      {!item && (
        <Field
          label={t("Opening stock")}
          name={`${id}qty`}
          value={form.quantity}
          onChange={set("quantity")}
          error={fieldErrors.quantity}
          hint={t("How many you have now. Leave empty for zero.")}
          required={false}
          inputMode="decimal"
        />
      )}
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : item ? t("Save changes") : t("Add item")}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}

function History({ item }: { item: InventoryItem }) {
  const [rows, setRows] = useState<Movement[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ movements: Movement[] }>(`/inventory/${item.id}/movements?limit=20`)
      .then((r) => setRows(r.movements))
      .catch((e) => setError(errorMessage(e, t("Couldn't load the history."))));
  }, [item.id, item.quantity_on_hand]);

  if (error) return <FormError message={error} />;
  if (!rows) return <p className="muted">{t("Loading…")}</p>;
  return (
    <ol className="activity inventory__history">
      {rows.map((m) => (
        <li key={m.id}>
          <time dateTime={m.created_at}>{formatWhen(m.created_at)}</time>
          <p>
            <strong>{KIND_LABEL[m.kind]}</strong>{" "}
            {t("{change}, leaving {quantity}", {
              change: `${Number(m.quantity_delta) > 0 ? "+" : ""}${qty(m.quantity_delta, item.unit)}`,
              quantity: qty(m.quantity_after, item.unit),
            })}
            {m.project_name ? ` — ${t("for {project}", { project: m.project_name })}` : ""}
            {m.note ? ` — ${m.note}` : ""}
            {m.created_by ? ` (${m.created_by})` : ""}
          </p>
        </li>
      ))}
    </ol>
  );
}

interface CountResult {
  item_id: number;
  name: string;
  unit: string;
  expected: string;
  counted: string;
  difference: string;
}

/** Count what's on the shelf; only items with a number entered are recorded. */
function StockCount({ org, onDone }: { org: Organization; onDone(): void }) {
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [counts, setCounts] = useState<Record<number, string>>({});
  const [showExpected, setShowExpected] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    results: CountResult[];
    changed_count: number;
    value_change: string;
    currency: string;
  } | null>(null);

  useEffect(() => {
    api<{ items: InventoryItem[] }>(`/organizations/${org.id}/inventory`)
      .then((r) => setItems(r.items))
      .catch((e) => setError(errorMessage(e)));
  }, [org.id]);

  const entered = Object.entries(counts).filter(([, v]) => v.trim() !== "");

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      const r = await api<typeof result>(`/organizations/${org.id}/inventory/counts`, {
        body: {
          note: note.trim() || null,
          counts: entered.map(([itemId, v]) => ({ item_id: Number(itemId), counted: v.trim().replace(",", ".") })),
        },
      });
      setResult(r);
    },
    (e) => setError(errorMessage(e)),
  );

  if (result) {
    const changed = result.results.filter((r) => Number(r.difference) !== 0);
    return (
      <section className="panel" aria-labelledby="count-done">
        <h2 id="count-done" className="panel__title">
          {t("Count saved")}
        </h2>
        <p>
          {result.changed_count === 0
            ? t("{count} items counted, no differences.", { count: result.results.length })
            : t("{count} items counted, {changed} different from the records.", {
                count: result.results.length,
                changed: result.changed_count,
              })}
          {result.changed_count > 0 &&
            ` ${t("Stock value changed by {amount}.", { amount: formatMoney(result.value_change, result.currency) })}`}
        </p>
        {changed.length > 0 && (
          <table className="report__table">
            <thead>
              <tr>
                <th scope="col">{t("Item")}</th>
                <th scope="col" className="num">
                  {t("Expected")}
                </th>
                <th scope="col" className="num">
                  {t("Counted")}
                </th>
                <th scope="col" className="num">
                  {t("Difference")}
                </th>
              </tr>
            </thead>
            <tbody>
              {changed.map((r) => (
                <tr key={r.item_id}>
                  <td>{r.name}</td>
                  <td className="num">{qty(r.expected, r.unit)}</td>
                  <td className="num">{qty(r.counted, r.unit)}</td>
                  <td className={Number(r.difference) < 0 ? "num overdue" : "num"}>
                    {Number(r.difference) > 0 ? "+" : ""}
                    {qty(r.difference, r.unit)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="form__actions inventory__done">
          <button type="button" className="btn btn--primary" onClick={onDone}>
            {t("Back to inventory")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <form onSubmit={submit} className="panel form" aria-labelledby="count-heading">
      <h2 id="count-heading" className="panel__title">
        {t("Stock count")}
      </h2>
      <p className="muted">
        {t("Enter what you count on the shelf. Items you leave empty aren't changed. Quantities are set to what you enter, and the differences are recorded.")}
      </p>
      <FormError message={error} />
      <FilterCheck label={t("Show expected quantities")} checked={showExpected} onChange={setShowExpected} />
      {!items && !error && <p className="muted">{t("Loading…")}</p>}
      {items && (
        <table className="report__table count-table">
          <thead>
            <tr>
              <th scope="col">{t("Item")}</th>
              {showExpected && (
                <th scope="col" className="num">
                  {t("Expected")}
                </th>
              )}
              <th scope="col" className="num">
                {t("Counted")}
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <td>
                  <label htmlFor={`count_${i.id}`}>{i.name}</label>
                  {i.location && <span className="muted"> — {i.location}</span>}
                </td>
                {showExpected && <td className="num">{qty(i.quantity_on_hand, i.unit)}</td>}
                <td className="num">
                  <input
                    id={`count_${i.id}`}
                    className="count-input"
                    inputMode="decimal"
                    value={counts[i.id] ?? ""}
                    onChange={(e) => setCounts((c) => ({ ...c, [i.id]: e.target.value }))}
                    aria-label={t("Counted {unit} of {name}", { unit: i.unit, name: i.name })}
                  />{" "}
                  <span className="muted">{i.unit}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Field
        label={t("Note")}
        name="count_note"
        value={note}
        onChange={setNote}
        hint={t("Defaults to \"Stock count\".")}
        required={false}
      />
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy || entered.length === 0}>
          {busy ? t("Saving…") : t("Save count ({count})", { count: entered.length })}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onDone}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
