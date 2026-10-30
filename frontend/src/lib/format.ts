const number = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Display only: the backend does all the arithmetic. */
export function formatMoney(amount: string, currency: string): string {
  return `${number.format(Number(amount))} ${currency}`;
}

export function formatPct(pct: string | null): string {
  return pct === null ? "N/A" : `${Math.round(Number(pct))}%`;
}

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return dateFmt.format(new Date(y, m - 1, d));
}

const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" });

/** "2026-10" -> "Oct 2026" */
export function formatMonth(yearMonth: string): string {
  const [y, m] = yearMonth.split("-").map(Number);
  return monthFmt.format(new Date(y, m - 1, 1));
}

export function formatDateRange(start: string | null, end: string | null): string | null {
  if (start && end) return `${formatDate(start)} to ${formatDate(end)}`;
  if (end) return `Ends ${formatDate(end)}`;
  if (start) return `Starts ${formatDate(start)}`;
  return null;
}

export const STATUS_LABEL: Record<string, string> = {
  planned: "Planned",
  active: "Active",
  on_hold: "On hold",
  completed: "Completed",
  archived: "Archived",
};

export const TASK_STATUS_LABEL: Record<string, string> = {
  todo: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

export const PRIORITY_LABEL: Record<string, string> = { low: "Low", medium: "Medium", high: "High" };

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  project_manager: "Project manager",
  contributor: "Contributor",
  viewer: "Viewer",
  system_admin: "System administrator",
};

/** Roles an owner can give, with what each one can do. */
export const ROLE_HINT: Record<string, string> = {
  owner: "Everything, including members and settings",
  project_manager: "Create and manage projects, tasks and expenses",
  contributor: "Add tasks and expenses; update their own",
  viewer: "Read only",
};

/** Where to go after logging in: only same-site paths, never "//host" or full URLs. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/app";
}
