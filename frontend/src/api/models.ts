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
  organization_id: number;
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
  /** only on GET /projects/:id */
  my_role?: Role;
}

export type ExpenseStatus = "valid" | "voided" | "refunded";

export interface Expense {
  id: number;
  project_id: number;
  created_by: number;
  category: string;
  amount: string;
  currency: string;
  description: string | null;
  expense_date: string;
  status: ExpenseStatus;
}

export type TaskStatus = "todo" | "in_progress" | "blocked" | "done" | "cancelled";
export type TaskPriority = "low" | "medium" | "high";

export interface Task {
  id: number;
  project_id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  assignee_id: number | null;
  assignee_name: string | null;
  completed_at: string | null;
  is_overdue: boolean;
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

/** Owners, project managers and contributors can record expenses and add tasks. */
export const canContribute = (role: Role) => canManageProjects(role) || role === "contributor";

export interface ToolTraceEntry {
  tool: string;
  arguments: Record<string, string | number | boolean>;
  ok: boolean;
}

export interface ChatReply {
  answer: string;
  tool_trace: ToolTraceEntry[];
  ai_generated: true;
}
