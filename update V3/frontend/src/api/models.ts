export type Role = "owner" | "project_manager" | "contributor" | "viewer" | "system_admin";

export interface Organization {
  id: number;
  name: string;
  default_currency: string;
  role: Role;
}

/** Money and percentages arrive as decimal strings (e.g. "12500.00") so no precision is lost. */
export interface Project {
  id: number;
  name: string;
  status: "planned" | "active" | "on_hold" | "completed" | "archived";
  currency: string;
  start_date: string | null;
  end_date: string | null;
  budget: string;
  actual: string;
  remaining: string;
  /** actual - budget; positive means over budget */
  variance: string;
  /** null when the budget is zero */
  consumed_pct: string | null;
  task_completion_pct: string | null;
  overdue_task_count: number;
  over_budget: boolean;
}

export interface CurrencyTotals {
  currency: string;
  budget: string;
  actual: string;
  remaining: string;
}

export interface DashboardSummary {
  totals: CurrencyTotals[];
  project_count: number;
  over_budget_project_count: number;
  overdue_task_count: number;
}

export const canManageProjects = (role: Role) => role === "owner" || role === "project_manager";
