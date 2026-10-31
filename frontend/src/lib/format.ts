import { getLocale, t } from "../i18n";

const number = new Intl.NumberFormat(getLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Display only: the backend does all the arithmetic. */
export function formatMoney(amount: string, currency: string): string {
  return `${number.format(Number(amount))} ${currency}`;
}

const quantity = new Intl.NumberFormat(getLocale(), { maximumFractionDigits: 2 });

/** Quantities and distances: up to two decimals, grouped the local way. */
export function formatNumber(value: string | number): string {
  return quantity.format(Number(value));
}

const percent = new Intl.NumberFormat(getLocale(), { style: "percent", maximumFractionDigits: 0 });

export function formatPct(pct: string | null): string {
  return pct === null ? t("N/A") : percent.format(Math.round(Number(pct)) / 100);
}

const dateFmt = new Intl.DateTimeFormat(getLocale(), { day: "numeric", month: "short", year: "numeric" });

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return dateFmt.format(new Date(y, m - 1, d));
}

const monthFmt = new Intl.DateTimeFormat(getLocale(), { month: "short", year: "numeric" });

/** "2026-10" -> "Oct 2026" */
export function formatMonth(yearMonth: string): string {
  const [y, m] = yearMonth.split("-").map(Number);
  return monthFmt.format(new Date(y, m - 1, 1));
}

export function formatDateRange(start: string | null, end: string | null): string | null {
  if (start && end) return t("{start} to {end}", { start: formatDate(start), end: formatDate(end) });
  if (end) return t("Ends {date}", { date: formatDate(end) });
  if (start) return t("Starts {date}", { date: formatDate(start) });
  return null;
}

export const STATUS_LABEL: Record<string, string> = {
  planned: t("Planned"),
  active: t("Active"),
  on_hold: t("On hold"),
  completed: t("Completed"),
  archived: t("Archived"),
};

export const TASK_STATUS_LABEL: Record<string, string> = {
  todo: t("To do"),
  in_progress: t("In progress"),
  blocked: t("Blocked"),
  done: t("Done"),
  cancelled: t("Cancelled"),
};

export const TRIP_STATUS_LABEL: Record<string, string> = {
  planned: t("Planned"),
  booked: t("Booked"),
  completed: t("Completed"),
  cancelled: t("Cancelled"),
};

export const PRIORITY_LABEL: Record<string, string> = { low: t("Low"), medium: t("Medium"), high: t("High") };

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const ROLE_LABEL: Record<string, string> = {
  owner: t("Owner"),
  project_manager: t("Project manager"),
  contributor: t("Contributor"),
  viewer: t("Viewer"),
  system_admin: t("System administrator"),
};

/** Roles an owner can give, with what each one can do. */
export const ROLE_HINT: Record<string, string> = {
  owner: t("Everything, including members and settings"),
  project_manager: t("Create and manage projects, tasks and expenses"),
  contributor: t("Add tasks and expenses; update their own"),
  viewer: t("Read only"),
};

/** Where to go after logging in: only same-site paths, never "//host" or full URLs. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/app";
}
