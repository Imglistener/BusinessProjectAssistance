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
  description: string | null;
  type: string | null;
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
  trip_id: number | null;
  attachment_count: number;
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
  milestone_id: number | null;
  completed_at: string | null;
  is_overdue: boolean;
}

export interface Milestone {
  id: number;
  project_id: number;
  title: string;
  due_date: string | null;
  status: "open" | "done";
  task_count: number;
  done_task_count: number;
  /** null when no eligible linked tasks */
  task_completion_pct: string | null;
  is_overdue: boolean;
}

export interface DeadlineItem {
  kind: "task" | "milestone" | "trip";
  id: number;
  title: string;
  due_date: string | null;
  /** negative when overdue */
  days_until_due: number | null;
  overdue: boolean;
  project_id: number;
  project_name: string;
  assignee?: string | null;
  priority?: TaskPriority;
  status?: TaskStatus;
}

export interface Deadlines {
  as_of: string;
  horizon_days: number;
  items: DeadlineItem[];
  item_count: number;
  my_tasks: DeadlineItem[];
  my_task_count: number;
}

export interface InventoryItem {
  id: number;
  name: string;
  sku: string | null;
  unit: string;
  unit_cost: string | null;
  currency: string;
  quantity_on_hand: string;
  reorder_level: string | null;
  location: string | null;
  description: string | null;
  archived: boolean;
  /** null when the item has no unit cost */
  stock_value: string | null;
  low_stock: boolean;
}

export interface InventorySummary {
  item_count: number;
  low_stock_count: number;
  stock_value: string;
  unpriced_item_count: number;
  currency: string;
}

export interface Movement {
  id: number;
  item_id: number;
  kind: "receive" | "issue" | "adjust" | "count";
  quantity_delta: string;
  quantity_after: string;
  project_id: number | null;
  project_name: string | null;
  note: string | null;
  created_by: string | null;
  created_at: string;
}

export type TripStatus = "planned" | "booked" | "completed" | "cancelled";
export type TripItemKind = "flight" | "train" | "car" | "hotel" | "meeting" | "other";

export interface TripItem {
  id: number;
  trip_id: number;
  kind: TripItemKind;
  title: string;
  date: string;
  /** local "HH:MM" */
  start_time: string | null;
  end_time: string | null;
  location: string | null;
  confirmation: string | null;
  estimated_cost: string | null;
  notes: string | null;
}

export interface Trip {
  id: number;
  project_id: number;
  title: string;
  destination: string;
  purpose: string | null;
  start_date: string;
  end_date: string;
  nights: number;
  status: TripStatus;
  currency: string;
  budget: string | null;
  estimated_cost: string;
  actual: string;
  remaining: string | null;
  over_budget: boolean;
  travelers: { user_id: number; name: string }[];
  item_count: number;
  created_by: number;
  /** only on GET /trips/:id */
  items?: TripItem[];
  expenses?: {
    id: number;
    category: string;
    amount: string;
    expense_date: string;
    description: string | null;
    status: ExpenseStatus;
  }[];
  project_name?: string;
  can_edit?: boolean;
}

export interface Attachment {
  id: number;
  expense_id: number;
  filename: string;
  content_type: string;
  size: number;
  uploaded_by: string | null;
  created_at: string;
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

export interface Member {
  user_id: number;
  name: string;
  role: Role;
  /** only returned to owners */
  email?: string;
}

export interface Invitation {
  id: number;
  email: string;
  role: Role;
  state: "pending" | "expired" | "accepted" | "revoked";
  created_at: string;
  expires_at: string;
}

export interface InvitationPreview {
  organization_name: string;
  role: Role;
  email: string;
  invited_by: string | null;
  state: Invitation["state"];
}

export const canManageMembers = (role: Role) => role === "owner";

export interface ReportTask {
  id: number;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  assignee: string | null;
  milestone: string | null;
  days_overdue: number | null;
}

export interface SpendingRow {
  group: string;
  total: string;
  expense_count: number;
  /** share of actual spend; null when nothing has been spent */
  share_pct: string | null;
}

export interface ProjectReport {
  generated_at: string;
  as_of: string;
  organization: { name: string; timezone: string };
  project: {
    id: number;
    name: string;
    description: string | null;
    status: Project["status"];
    owner: string | null;
    start_date: string | null;
    end_date: string | null;
    currency: string;
  };
  budget: {
    approved: string;
    actual: string;
    remaining: string;
    variance: string;
    consumed_pct: string | null;
    over_budget: boolean;
    valid_expense_count: number;
    excluded_expense_count: number;
  };
  spending_by_category: SpendingRow[];
  spending_by_month: SpendingRow[];
  tasks: {
    total: number;
    by_status: Partial<Record<TaskStatus, number>>;
    completion_pct: string | null;
    overdue: ReportTask[];
    upcoming: ReportTask[];
  };
  milestones: {
    title: string;
    due_date: string | null;
    status: "open" | "done";
    is_overdue: boolean;
    task_count: number;
    task_completion_pct: string | null;
  }[];
  definitions: Record<string, string>;
}
