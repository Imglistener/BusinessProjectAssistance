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
