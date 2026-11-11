import {
  ArrowLeftRight,
  Boxes,
  ClipboardList,
  History,
  Archive,
  ArchiveRestore,
  MoreHorizontal,
  PackageMinus,
  PackagePlus,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  Truck,
  Warehouse as WarehouseIcon,
} from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import {
  canContribute,
  canManageProjects,
  type InventoryItem,
  type InventorySummary,
  type Organization,
  type Project,
  type Warehouse,
} from "../api/models";
import { useOrg } from "../auth/OrgContext";
import { AnimatedMoney } from "../components/AnimatedMoney";
import { AppShell } from "../components/AppShell";
import { useDebounced } from "../components/Filters";
import { FormAlert, SimpleSelect } from "../components/form";
import {
  DeleteItemDialog,
  HistoryDialog,
  ItemFormDialog,
  MoveDialog,
  MovementDialog,
  TransferDialog,
  type MovementKind,
} from "../components/inventory/ItemDialogs";
import { StockCountDialog } from "../components/inventory/StockCountDialog";
import { Warehouses } from "../components/inventory/Warehouses";
import { errorMessage } from "../lib/errors";
import { formatMoney, formatNumber } from "../lib/format";
import { t } from "../i18n";
import { tx } from "../i18n/rich";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

interface Listing {
  items: InventoryItem[];
  summary: InventorySummary;
  warehouses: Warehouse[];
  scope: { project_id: number | null; project_name: string | null };
}

type Open =
  | { kind: "add" }
  | { kind: "edit" | "transfer" | "move" | "history"; item: InventoryItem }
  | { kind: "movement"; item: InventoryItem; movement: MovementKind }
  | { kind: "count" }
  | null;

export default function Inventory() {
  const { orgs, org, error } = useOrg();
  return (
    <AppShell legacy={false}>
      <div className="mx-auto grid w-full max-w-7xl gap-6 p-4 md:p-8">
        <FormAlert message={error} />
        {orgs === null && !error && <Skeleton className="h-96" />}
        {orgs !== null && !org && (
          <p className="text-sm text-muted-foreground">
            {tx("Create your organization on the {dashboard} first.", {
              dashboard: (
                <Link to="/app" className="font-medium text-primary underline-offset-4 hover:underline">
                  {t("dashboard")}
                </Link>
              ),
            })}
          </p>
        )}
        {org && <InventoryManager key={org.id} org={org} />}
      </div>
    </AppShell>
  );
}

function InventoryManager({ org }: { org: Organization }) {
  const [params, setParams] = useSearchParams();
  const scope = params.get("scope") ?? "general";
  const [projects, setProjects] = useState<Project[]>([]);
  const [data, setData] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [archived, setArchived] = useState(false);
  const [open, setOpen] = useState<Open>(null);
  const [deleting, setDeleting] = useState<InventoryItem | null>(null);
  const [tab, setTab] = useState(params.get("tab") === "warehouses" ? "warehouses" : "items");
  const q = useDebounced(search.trim());

  useEffect(() => {
    api<{ projects: Project[] }>(`/organizations/${org.id}/projects?include_archived=true&sort=name`)
      .then((r) => setProjects(r.projects))
      .catch(() => setProjects([]));
  }, [org.id]);

  const load = useCallback(() => {
    const query = new URLSearchParams({ scope });
    if (q) query.set("q", q);
    if (lowOnly) query.set("low_stock", "true");
    if (archived) query.set("include_archived", "true");
    api<Listing>(`/organizations/${org.id}/inventory?${query}`)
      .then((r) => {
        setError(null);
        setData(r);
      })
      .catch((e) => setError(errorMessage(e, t("Couldn't load the inventory."))));
  }, [org.id, scope, q, lowOnly, archived]);

  useEffect(load, [load]);

  const done = () => {
    setOpen(null);
    load();
  };

  const project = scope === "general" ? null : projects.find((p) => String(p.id) === scope) ?? null;
  const readOnly = project?.status === "archived";
  const canUse = canContribute(org.role) && !readOnly;
  const canManage = canManageProjects(org.role) && !readOnly;
  const projectId = scope === "general" ? null : Number(scope);
  const warehouses = data?.warehouses ?? [];
  const currency = data?.summary.currency ?? org.default_currency;
  const items = data?.items ?? [];

  const scopeOptions = [
    { value: "general", label: t("General stock") },
    ...projects.map((p) => ({ value: String(p.id), label: p.status === "archived" ? t("{name} (archived)", { name: p.name }) : p.name })),
  ];

  return (
    <>
      <motion.header
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="flex flex-wrap items-end justify-between gap-4"
      >
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{t("Inventory")}</h1>
          <p className="text-sm text-muted-foreground">
            {scope === "general"
              ? t("General stock is the organization's own; each project also has its own inventory.")
              : t("The inventory of {project}.", { project: project?.name ?? "…" })}{" "}
            {t("Values in {currency}.", { currency: org.default_currency })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:flex-nowrap">
          <SimpleSelect
            ariaLabel={t("Inventory")}
            value={scope}
            onChange={(v) => {
              setParams(v === "general" ? {} : { scope: v });
              setData(null);
            }}
            options={scopeOptions}
            className="w-64"
          />
          {canUse && (
            <Button variant="outline" onClick={() => setOpen({ kind: "count" })} disabled={!items.length}>
              <ClipboardList className="size-4" />
              {t("Stock count")}
            </Button>
          )}
          {canManage && (
            <Button onClick={() => setOpen({ kind: "add" })}>
              <Plus className="size-4" />
              {t("Add item")}
            </Button>
          )}
        </div>
      </motion.header>

      {readOnly && (
        <p className="rounded-lg border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          {t("This project is archived, so its inventory is read-only.")}
        </p>
      )}
      <FormAlert message={error} />

      <section aria-label={t("Inventory totals")} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data === null ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <Stat i={0} icon={<Boxes className="size-4" />} label={t("Items in stock")} value={String(data.summary.item_count)} />
            <Stat i={1} icon={<PackagePlus className="size-4" />} label={t("Stock value")}
              value={<AnimatedMoney amount={data.summary.stock_value} currency={currency} />} />
            <Stat i={2} icon={<PackageMinus className="size-4" />} label={t("Low stock")} value={String(data.summary.low_stock_count)}
              tone={data.summary.low_stock_count > 0 ? "warn" : undefined} />
            <Stat i={3} icon={<WarehouseIcon className="size-4" />} label={t("Warehouses")} value={String(warehouses.length)} />
          </>
        )}
      </section>
      {data && data.summary.unpriced_item_count > 0 && (
        <p className="-mt-2 text-xs text-muted-foreground">
          {t("{count} items have no unit cost, so they aren't in the stock value.", { count: data.summary.unpriced_item_count })}
        </p>
      )}

      <Tabs
        value={tab}
        onValueChange={(v) => {
          setTab(v);
          const next = new URLSearchParams(params);
          if (v === "warehouses") next.set("tab", "warehouses");
          else next.delete("tab");
          setParams(next, { replace: true });
        }}
      >
        <TabsList>
          <TabsTrigger value="items">
            {t("Items")}
            {data && <span className="tabular ms-1.5 text-xs text-muted-foreground">{data.summary.item_count}</span>}
          </TabsTrigger>
          <TabsTrigger value="warehouses">
            {t("Warehouses")}
            {data && <span className="tabular ms-1.5 text-xs text-muted-foreground">{warehouses.length}</span>}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="items" className="mt-4 grid gap-4">
          <div role="search" aria-label={t("Filter items")} className="flex flex-wrap items-center gap-4">
            <div className="relative min-w-64 flex-1">
              <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input type="search" value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100}
                placeholder={t("Name, SKU or location")} aria-label={t("Search")} className="ps-9" />
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={lowOnly} onCheckedChange={(v) => setLowOnly(v === true)} />
              {t("Only low stock")}
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={archived} onCheckedChange={(v) => setArchived(v === true)} />
              {t("Show archived")}
            </label>
          </div>

          {data === null && !error && (
            <div className="grid gap-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
          )}
          {data && items.length === 0 && (
            <Card className="border-dashed">
              <CardContent className="grid justify-items-center gap-2 py-12 text-center">
                <span className="flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Boxes className="size-5" />
                </span>
                <p className="font-medium">{search || lowOnly ? t("No items match these filters.") : t("No items yet.")}</p>
                {!search && !lowOnly && (
                  <p className="max-w-sm text-sm text-muted-foreground">
                    {t("No items yet. Add what you keep in stock, with a reorder level to get low-stock warnings.")}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
          {items.length > 0 && (
            <ul className="grid gap-3">
              {items.map((item, i) => (
                <ItemRow
                  key={item.id}
                  index={i}
                  item={item}
                  currency={currency}
                  canUse={canUse && !item.archived}
                  canManage={canManage}
                  hasWarehouses={warehouses.length > 0}
                  onOpen={setOpen}
                  onDelete={() => setDeleting(item)}
                  onArchive={async () => {
                    try {
                      await api(`/inventory/${item.id}`, { method: "PATCH", body: { archived: !item.archived } });
                      load();
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                />
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="warehouses" className="mt-4">
          <Warehouses orgId={org.id} projectId={projectId} warehouses={warehouses} currency={currency} canManage={canManage} onChanged={load} />
        </TabsContent>
      </Tabs>

      <ItemFormDialog
        open={open?.kind === "add" || open?.kind === "edit"}
        onOpenChange={(o) => !o && setOpen(null)}
        orgId={org.id}
        projectId={projectId}
        item={open?.kind === "edit" ? open.item : null}
        warehouses={warehouses}
        currency={currency}
        onSaved={done}
      />
      {open?.kind === "movement" && (
        <MovementDialog open onOpenChange={(o) => !o && setOpen(null)} kind={open.movement} item={open.item}
          warehouses={warehouses} projects={projects.filter((p) => p.status !== "archived")} onSaved={done} />
      )}
      {open?.kind === "transfer" && (
        <TransferDialog open onOpenChange={(o) => !o && setOpen(null)} item={open.item} warehouses={warehouses} onSaved={done} />
      )}
      {open?.kind === "move" && (
        <MoveDialog open onOpenChange={(o) => !o && setOpen(null)} orgId={org.id} item={open.item} warehouses={warehouses}
          projects={projects} onSaved={done} />
      )}
      {open?.kind === "history" && <HistoryDialog open onOpenChange={(o) => !o && setOpen(null)} item={open.item} />}
      <StockCountDialog open={open?.kind === "count"} onOpenChange={(o) => !o && setOpen(null)} orgId={org.id}
        items={items.filter((i) => !i.archived)} warehouses={warehouses} onSaved={load} />
      <DeleteItemDialog item={deleting} onClose={() => setDeleting(null)} onDeleted={load} />
    </>
  );
}

function Stat({ i, icon, label, value, tone }: { i: number; icon: ReactNode; label: string; value: ReactNode; tone?: "warn" }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05 * (i + 1) }}>
      <Card className="gap-2 py-5">
        <CardContent className="grid gap-2">
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className={cn("flex size-7 items-center justify-center rounded-lg bg-muted", tone === "warn" && "bg-warning/15 text-amber-600 dark:text-amber-300")}>
              {icon}
            </span>
            {label}
          </span>
          <span className={cn("tabular text-2xl font-semibold", tone === "warn" && "text-amber-600 dark:text-amber-300")}>{value}</span>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function ItemRow({
  index,
  item,
  currency,
  canUse,
  canManage,
  hasWarehouses,
  onOpen,
  onDelete,
  onArchive,
}: {
  index: number;
  item: InventoryItem;
  currency: string;
  canUse: boolean;
  canManage: boolean;
  hasWarehouses: boolean;
  onOpen(open: Open): void;
  onDelete(): void;
  onArchive(): void;
}) {
  const meta = [item.sku, item.location].filter(Boolean).join(" · ");
  const notInWarehouse = Number(item.not_in_warehouse);
  return (
    <motion.li
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index, 8) * 0.03 }}
    >
      <Card className={cn("gap-3 py-4", item.archived && "opacity-70")}>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="grid min-w-0 gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="item-name font-medium">{item.name}</h3>
                {item.low_stock && (
                  <Badge variant="secondary" className="rounded-md border-0 bg-warning/15 text-amber-700 dark:text-amber-300">
                    {t("Low stock")}
                  </Badge>
                )}
                {item.archived && (
                  <Badge variant="secondary" className="rounded-md">
                    {t("Archived")}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {[
                  meta,
                  item.unit_cost ? t("{price} per {unit}", { price: formatMoney(item.unit_cost, currency), unit: item.unit }) : t("No unit cost"),
                  item.reorder_level && t("reorder at {quantity}", { quantity: `${formatNumber(item.reorder_level)} ${item.unit}` }),
                ]
                  .filter(Boolean)
                  .join(" — ")}
              </p>
            </div>
            <div className="grid justify-items-end">
              <span className="tabular text-lg font-semibold">
                {formatNumber(item.quantity_on_hand)} <span className="text-sm font-normal text-muted-foreground">{item.unit}</span>
              </span>
              {item.stock_value && <span className="tabular text-xs text-muted-foreground">{formatMoney(item.stock_value, currency)}</span>}
            </div>
          </div>

          {(item.stock.length > 0 || (hasWarehouses && notInWarehouse !== 0)) && (
            <ul className="flex flex-wrap gap-2" aria-label={t("Stock by warehouse")}>
              {item.stock.map((s) => (
                <li key={s.warehouse_id} className="tabular inline-flex items-center gap-1.5 rounded-full border bg-muted/40 px-2.5 py-0.5 text-xs">
                  <WarehouseIcon className="size-3 text-primary" />
                  {s.warehouse} · {formatNumber(s.quantity)}
                </li>
              ))}
              {notInWarehouse !== 0 && (
                <li className="tabular inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-0.5 text-xs text-muted-foreground">
                  {t("Not in a warehouse")} · {formatNumber(item.not_in_warehouse)}
                </li>
              )}
            </ul>
          )}

          {(canUse || canManage) && (
            <div className="flex flex-wrap items-center gap-2">
              {canUse && (
                <>
                  <Button size="sm" variant="outline" onClick={() => onOpen({ kind: "movement", item, movement: "receive" })}>
                    <PackagePlus className="size-4" />
                    {t("Receive")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => onOpen({ kind: "movement", item, movement: "issue" })}>
                    <PackageMinus className="size-4" />
                    {t("Issue")}
                  </Button>
                  {hasWarehouses && (
                    <Button size="sm" variant="ghost" onClick={() => onOpen({ kind: "transfer", item })}>
                      <ArrowLeftRight className="size-4" />
                      {t("Transfer")}
                    </Button>
                  )}
                </>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" variant="ghost" aria-label={t("More actions for {name}", { name: item.name })}>
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-48">
                  {canManage && !item.archived && (
                    <DropdownMenuItem onSelect={() => onOpen({ kind: "movement", item, movement: "adjust" })}>
                      <SlidersHorizontal className="size-4" />
                      {t("Adjust")}
                    </DropdownMenuItem>
                  )}
                  {canManage && !item.archived && (
                    <DropdownMenuItem onSelect={() => onOpen({ kind: "move", item })}>
                      <Truck className="size-4" />
                      {t("Move to another inventory")}
                    </DropdownMenuItem>
                  )}
                  {canManage && (
                    <DropdownMenuItem onSelect={() => onOpen({ kind: "edit", item })}>
                      <Pencil className="size-4" />
                      {t("Edit")}
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onSelect={() => onOpen({ kind: "history", item })}>
                    <History className="size-4" />
                    {t("History")}
                  </DropdownMenuItem>
                  {canManage && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onSelect={onArchive}>
                        {item.archived ? <ArchiveRestore className="size-4" /> : <Archive className="size-4" />}
                        {item.archived ? t("Restore") : t("Archive")}
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={onDelete} className="text-destructive focus:text-destructive">
                        <Trash2 className="size-4" />
                        {t("Delete")}
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.li>
  );
}
