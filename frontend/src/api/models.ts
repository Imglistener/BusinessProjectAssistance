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

/** How much of an item one warehouse holds. */
export interface WarehouseStock {
  warehouse_id: number;
  warehouse: string;
  quantity: string;
}

export interface InventoryItem {
  id: number;
  /** the project whose inventory it's in; null for General stock */
  project_id: number | null;
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
  /** warehouses holding some of it */
  stock: WarehouseStock[];
  not_in_warehouse: string;
}

/** A place where stock is kept, in General stock or a project's inventory. */
export interface Warehouse {
  id: number;
  project_id: number | null;
  name: string;
  address: string | null;
  lat: number | null;
  lng: number | null;
  notes: string | null;
  item_count: number;
  units: string;
  value: string;
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
  kind: "receive" | "issue" | "adjust" | "count" | "transfer" | "move_out" | "move_in";
  quantity_delta: string;
  quantity_after: string;
  project_id: number | null;
  project_name: string | null;
  warehouse: string | null;
  to_warehouse: string | null;
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

export interface TripRoute {
  origin: string | null;
  origin_lat: number | null;
  origin_lng: number | null;
  destination_lat: number | null;
  destination_lng: number | null;
  /** one way, km */
  distance_km: string | null;
  distance_source: "route" | "straight_line" | "manual" | null;
  vehicle_type: string | null;
  vehicle_count: number;
  round_trip: boolean;
  fuel_city: string | null;
}

export interface Range {
  low: string;
  expected: string;
  high: string;
}

export interface FuelEstimate {
  currency: string;
  vehicle: {
    type: string;
    label: string;
    fuel: "petrol" | "diesel";
    l_per_100km_low: string;
    l_per_100km_high: string;
  };
  vehicle_count: number;
  round_trip: boolean;
  one_way_km: string;
  total_km: string;
  distance_source: string;
  fuel_price: { price_per_litre: string; city: string | null; as_of: string; stale: boolean };
  litres: Range;
  cost: Range;
  assumptions: string[];
  warnings: string[];
}

export interface VehicleProfile {
  type: string;
  label: string;
  fuel: "petrol" | "diesel";
  l_per_100km_low: string;
  l_per_100km_high: string;
}

export interface TravelReference {
  vehicles: VehicleProfile[];
  default_vehicle: string;
  cities: { name: string; lat: number; lng: number }[];
  road_factor: string;
}

export interface FuelPrice {
  id: number;
  /** null = default for any city */
  city: string | null;
  fuel_type: "petrol" | "diesel";
  price_per_litre: string;
  currency: string;
  as_of: string;
  stale: boolean;
  /** "teraedge" when read from prix-gasoil-maroc.teraedge.ma, else "manual" */
  source: string;
  fetched_at: string | null;
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
  route: TripRoute;
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

export interface AppNotification {
  id: number;
  kind: "task_assigned" | "trip_traveler" | "low_stock" | "project_over_budget" | "invite_accepted" | string;
  title: string;
  body: string | null;
  /** frontend path to open */
  link: string | null;
  organization_id: number;
  organization_name: string | null;
  created_at: string;
  read: boolean;
}

export interface CurrencyTotals {
  currency: string;
  budget: string;
  actual: string;
  remaining: string;
  /** null when the budget is zero */
  consumed_pct: string | null;
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

/** A new project's opening stock (typed in, or drafted by the assistant). */
export interface OpeningItem {
  name: string;
  unit: string;
  quantity: string | null;
  unit_cost: string | null;
  reorder_level?: string | null;
}

export interface ProjectPlan {
  inventory?: OpeningItem[];
  name: string;
  description: string | null;
  currency: string;
  budget: string | null;
  start_date: string | null;
  end_date: string | null;
  milestones: { title: string; due_date: string | null }[];
  tasks: {
    title: string;
    description: string | null;
    priority: TaskPriority;
    due_date: string | null;
    milestone: string | null;
  }[];
}

export interface ChatReply {
  answer: string;
  tool_trace: ToolTraceEntry[];
  /** Projects the assistant drafted; nothing is created until the user confirms. */
  proposals?: ProjectPlan[];
  /** Stock changes the assistant drafted; nothing changes until the user confirms. */
  stock_proposals?: StockDraft[];
  ai_generated: true;
}

export type StockChangeKind = "receive" | "issue" | "adjust" | "create" | "transfer" | "move" | "delete";

/** One drafted stock change, already matched to an item and project, with a preview of the result. */
export interface StockDraftLine {
  kind: StockChangeKind;
  /** which inventory the line is in: a project's, or General stock (null) */
  inventory_project_id: number | null;
  inventory_name: string;
  warehouse_id: number | null;
  warehouse_name: string | null;
  /** transfer and move: destination warehouse (null = not in a warehouse) */
  to_warehouse_id: number | null;
  to_warehouse_name: string | null;
  /** move: destination inventory */
  to_project_id: number | null;
  to_inventory_name: string | null;
  /** null for "create" (a new item) and for lines whose item wasn't found */
  item_id: number | null;
  name: string | null;
  unit: string | null;
  /** positive, except "adjust" (signed); for "create", the opening stock */
  quantity: string | null;
  on_hand_before: string | null;
  on_hand_after: string | null;
  project_id: number | null;
  project_name: string | null;
  note: string | null;
  sku: string | null;
  location: string | null;
  unit_cost: string | null;
  reorder_level: string | null;
  low_after: boolean;
  /** false when only an owner or project manager may confirm this line */
  allowed: boolean;
  /** why the line can't be applied as drafted, in the reader's language */
  error: string | null;
}

export interface StockDraft {
  lines: StockDraftLine[];
  can_apply: boolean;
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
