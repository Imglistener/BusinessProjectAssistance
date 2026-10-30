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
import { formatMoney } from "../lib/format";

const qty = (q: string, unit: string) => `${Number(q).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${unit}`;
const KIND_LABEL: Record<string, string> = {
  receive: "Received",
  issue: "Issued",
  adjust: "Adjusted",
  count: "Counted",
};

export default function Inventory() {
  const { orgs, org, error } = useOrg();
  return (
    <AppShell>
      <header className="main__header">
        <h1>Inventory</h1>
        {org && (
          <p className="main__org">
            Stock kept by {org.name}. Values in {org.default_currency}.
          </p>
        )}
      </header>
      <FormError message={error} />
      {orgs === null && !error && <p className="muted">Loading…</p>}
      {orgs !== null && !org && (
        <p className="muted">
          Create your organization on the <Link to="/app">dashboard</Link> first.
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
      .catch((e) => setError(errorMessage(e, "Couldn't load the inventory.")));
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
        <section className="totals" aria-label="Inventory totals">
          <div>
            <span className="totals__label">Items in stock</span>
            <span className="totals__value">{summary.item_count}</span>
          </div>
          <div>
            <span className="totals__label">Stock value</span>
            <span className="totals__value">{formatMoney(summary.stock_value, summary.currency)}</span>
          </div>
          <div>
            <span className="totals__label">Low stock</span>
            <span className={summary.low_stock_count > 0 ? "totals__value totals__value--over" : "totals__value"}>
              {summary.low_stock_count}
            </span>
          </div>
        </section>
      )}
      {summary && summary.unpriced_item_count > 0 && (
        <p className="muted inventory__note">
          {summary.unpriced_item_count} {summary.unpriced_item_count === 1 ? "item has" : "items have"} no unit cost, so
          {summary.unpriced_item_count === 1 ? " it isn't" : " they aren't"} in the stock value.
        </p>
      )}

      <FormError message={error} />

      <section className="projects-section" aria-labelledby="items-heading">
        <div className="section-head">
          <h2 id="items-heading">Items</h2>
          <div className="form__actions">
            {canMove && items && items.length > 0 && mode === "list" && (
              <button type="button" className="btn btn--secondary" onClick={() => setMode("count")}>
                Stock count
              </button>
            )}
            {canManage && mode === "list" && (
              <button type="button" className="btn btn--primary" onClick={() => setMode("add")}>
                Add item
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

        <FilterBar label="Filter items">
          <label className="filter filter--grow">
            <span className="filter__label">Search</span>
            <input
              type="search"
              placeholder="Name, SKU or location"
              value={search}
              maxLength={100}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <FilterCheck label="Only low stock" checked={lowOnly} onChange={setLowOnly} />
          <FilterCheck label="Show archived" checked={showArchived} onChange={setShowArchived} />
        </FilterBar>

        {items === null && !error && <p className="muted">Loading…</p>}
        {items && items.length === 0 && (
          <p className="muted">
            {q || lowOnly
              ? "No items match these filters."
              : canManage
                ? "No items yet. Add what you keep in stock, with a reorder level to get low-stock warnings."
                : "No items yet."}
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
            {item.low_stock && <span className="tag tag--warn">Low stock</span>}
            {item.archived && <span className="tag">Archived</span>}
          </p>
          <p className="row__meta">
            {meta ? `${meta} — ` : ""}
            {item.unit_cost ? `${formatMoney(item.unit_cost, item.currency)} per ${item.unit}` : "No unit cost"}
            {item.reorder_level ? ` — reorder at ${qty(item.reorder_level, item.unit)}` : ""}
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
              Receive
            </button>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "issue" ? null : "issue")}>
              Issue
            </button>
          </>
        )}
        {!item.archived && canManage && (
          <>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "adjust" ? null : "adjust")}>
              Adjust
            </button>
            <button type="button" className="link-btn" onClick={() => setPanel(panel === "edit" ? null : "edit")}>
              Edit
            </button>
          </>
        )}
        <button type="button" className="link-btn" onClick={() => setPanel(panel === "history" ? null : "history")}>
          History
        </button>
        {canManage && (
          <button type="button" className="link-btn" onClick={toggleArchive}>
            {item.archived ? "Restore" : "Archive"}
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
  const title = { receive: "Receive stock", issue: "Issue stock", adjust: "Adjust stock" }[kind];

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
          label={kind === "adjust" ? `Change (${item.unit}, use - to remove)` : `Quantity (${item.unit})`}
          name={`${id}qty`}
          value={quantity}
          onChange={setQuantity}
          error={fieldErrors.quantity}
          inputMode="decimal"
        />
        {kind === "issue" ? (
          <SelectField
            label="For project"
            name={`${id}project`}
            value={projectId}
            onChange={setProjectId}
            options={[
              { value: "", label: "No project" },
              ...projects.map((p) => ({ value: String(p.id), label: p.name })),
            ]}
          />
        ) : (
          <Field
            label={kind === "adjust" ? "Reason" : "Note"}
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
          label="Note"
          name={`${id}note`}
          value={note}
          onChange={setNote}
          error={fieldErrors.note}
          required={false}
        />
      )}
      {fieldErrors.project_id && <p className="field__message field__message--error">{fieldErrors.project_id}</p>}
      <p className="muted">On hand now: {qty(item.quantity_on_hand, item.unit)}.</p>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : title}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
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
    <form onSubmit={submit} className="panel form inventory__form" aria-label={item ? "Edit item" : "Add item"}>
      <h3 className="panel__title">{item ? "Edit item" : "Add item"}</h3>
      <FormError message={error} />
      <div className="form__row">
        <Field label="Name" name={`${id}name`} value={form.name} onChange={set("name")} error={fieldErrors.name} />
        <Field
          label="SKU"
          name={`${id}sku`}
          value={form.sku}
          onChange={set("sku")}
          error={fieldErrors.sku}
          required={false}
        />
      </div>
      <div className="form__row">
        <Field
          label="Unit"
          name={`${id}unit`}
          value={form.unit}
          onChange={set("unit")}
          error={fieldErrors.unit}
          hint="pcs, box, kg, litre…"
          maxLength={20}
        />
        <Field
          label={`Unit cost (${org.default_currency})`}
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
          label="Reorder level"
          name={`${id}reorder`}
          value={form.reorder_level}
          onChange={set("reorder_level")}
          error={fieldErrors.reorder_level}
          hint="Warn when stock gets this low."
          required={false}
          inputMode="decimal"
        />
        <Field
          label="Location"
          name={`${id}location`}
          value={form.location}
          onChange={set("location")}
          error={fieldErrors.location}
          required={false}
        />
      </div>
      {!item && (
        <Field
          label="Opening stock"
          name={`${id}qty`}
          value={form.quantity}
          onChange={set("quantity")}
          error={fieldErrors.quantity}
          hint="How many you have now. Leave empty for zero."
          required={false}
          inputMode="decimal"
        />
      )}
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : item ? "Save changes" : "Add item"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
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
      .catch((e) => setError(errorMessage(e, "Couldn't load the history.")));
  }, [item.id, item.quantity_on_hand]);

  if (error) return <FormError message={error} />;
  if (!rows) return <p className="muted">Loading…</p>;
  return (
    <ol className="activity inventory__history">
      {rows.map((m) => (
        <li key={m.id}>
          <time dateTime={m.created_at}>{formatWhen(m.created_at)}</time>
          <p>
            <strong>{KIND_LABEL[m.kind]}</strong> {Number(m.quantity_delta) > 0 ? "+" : ""}
            {qty(m.quantity_delta, item.unit)}, leaving {qty(m.quantity_after, item.unit)}
            {m.project_name ? ` — for ${m.project_name}` : ""}
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
          Count saved
        </h2>
        <p>
          {result.results.length} {result.results.length === 1 ? "item" : "items"} counted,{" "}
          {result.changed_count === 0 ? "no differences." : `${result.changed_count} different from the records.`}
          {result.changed_count > 0 && ` Stock value changed by ${formatMoney(result.value_change, result.currency)}.`}
        </p>
        {changed.length > 0 && (
          <table className="report__table">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col" className="num">
                  Expected
                </th>
                <th scope="col" className="num">
                  Counted
                </th>
                <th scope="col" className="num">
                  Difference
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
            Back to inventory
          </button>
        </div>
      </section>
    );
  }

  return (
    <form onSubmit={submit} className="panel form" aria-labelledby="count-heading">
      <h2 id="count-heading" className="panel__title">
        Stock count
      </h2>
      <p className="muted">
        Enter what you count on the shelf. Items you leave empty aren't changed. Quantities are set to what you enter,
        and the differences are recorded.
      </p>
      <FormError message={error} />
      <FilterCheck label="Show expected quantities" checked={showExpected} onChange={setShowExpected} />
      {!items && !error && <p className="muted">Loading…</p>}
      {items && (
        <table className="report__table count-table">
          <thead>
            <tr>
              <th scope="col">Item</th>
              {showExpected && (
                <th scope="col" className="num">
                  Expected
                </th>
              )}
              <th scope="col" className="num">
                Counted
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
                    aria-label={`Counted ${i.unit} of ${i.name}`}
                  />{" "}
                  <span className="muted">{i.unit}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Field
        label="Note"
        name="count_note"
        value={note}
        onChange={setNote}
        hint='Defaults to "Stock count".'
        required={false}
      />
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy || entered.length === 0}>
          {busy ? "Saving…" : `Save count (${entered.length})`}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}
