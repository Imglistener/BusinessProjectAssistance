import { ArrowRight, Boxes, Warehouse as WarehouseIcon } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { InventorySummary } from "../api/models";
import { formatMoney } from "../lib/format";
import { t } from "../i18n";
import { Button } from "@/components/ui/button";

type Summary = InventorySummary & { warehouse_count: number };

/** The project's own inventory at a glance, with a way into it. */
export function ProjectInventoryCard({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) {
  const [s, setS] = useState<Summary | null>(null);
  useEffect(() => {
    api<{ summary: Summary }>(`/projects/${projectId}/inventory-summary`)
      .then((r) => setS(r.summary))
      .catch(() => setS(null));
  }, [projectId, refreshKey]);
  if (!s) return null;
  const empty = s.item_count === 0 && s.warehouse_count === 0;
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      aria-labelledby="project-inventory-heading"
      className="grid gap-4 rounded-xl border bg-card p-5 text-card-foreground shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Boxes className="size-4" />
          </span>
          <div>
            <h2 id="project-inventory-heading" className="text-base font-semibold">
              {t("Inventory")}
            </h2>
            <p className="text-xs text-muted-foreground">
              {empty ? t("This project has no stock or warehouses of its own yet.") : t("Stock and warehouses that belong to this project.")}
            </p>
          </div>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={`/app/inventory?scope=${projectId}`}>
            {empty ? t("Set up inventory") : t("Open inventory")}
            <ArrowRight className="size-3.5 rtl:rotate-180" />
          </Link>
        </Button>
      </div>
      {!empty && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Figure label={t("Items")} value={String(s.item_count)} />
          <Figure label={t("Stock value")} value={formatMoney(s.stock_value, s.currency)} />
          <Figure label={t("Low stock")} value={String(s.low_stock_count)} warn={s.low_stock_count > 0} />
          <Figure label={t("Warehouses")} value={String(s.warehouse_count)} icon />
        </dl>
      )}
    </motion.section>
  );
}

function Figure({ label, value, warn, icon }: { label: string; value: string; warn?: boolean; icon?: boolean }) {
  return (
    <div className="grid gap-0.5 rounded-lg bg-muted/50 px-3 py-2">
      <dt className="flex items-center gap-1 text-xs text-muted-foreground">
        {icon && <WarehouseIcon className="size-3" />}
        {label}
      </dt>
      <dd className={`tabular font-semibold ${warn ? "text-amber-600 dark:text-amber-300" : ""}`}>{value}</dd>
    </div>
  );
}
