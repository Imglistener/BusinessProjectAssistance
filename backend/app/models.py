import enum
from datetime import datetime, timezone

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    OWNER = "owner"
    PROJECT_MANAGER = "project_manager"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"
    SYSTEM_ADMIN = "system_admin"


class ProjectStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExpenseStatus(str, enum.Enum):
    VALID = "valid"
    VOIDED = "voided"
    REFUNDED = "refunded"


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40))
    # "en", "fr" or "ar": the language of emails and notifications (the app's own picker sets it).
    locale = db.Column(db.String(5), nullable=False, default="en", server_default="en")
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class PasswordResetToken(db.Model):
    """Single-use reset link. Only a SHA-256 of the token is stored."""

    __tablename__ = "password_reset_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))


class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    default_currency = db.Column(db.String(3), nullable=False, default="MAD")
    timezone = db.Column(db.String(64), nullable=False, default="Africa/Casablanca")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class OrganizationMember(db.Model):
    __tablename__ = "organization_members"
    __table_args__ = (db.UniqueConstraint("organization_id", "user_id"),)
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.Enum(Role), nullable=False, default=Role.VIEWER)
    status = db.Column(db.String(20), nullable=False, default="active")
    joined_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class OrganizationInvitation(db.Model):
    """A link-based invite. Only a SHA-256 of the token is stored; the link is shown once."""

    __tablename__ = "organization_invitations"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    role = db.Column(db.Enum(Role), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    invited_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending / accepted / revoked
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    accepted_at = db.Column(db.DateTime(timezone=True))


class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(60))
    description = db.Column(db.Text)
    status = db.Column(db.Enum(ProjectStatus), nullable=False, default=ProjectStatus.PLANNED)
    budget = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default="MAD")
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class ProjectMember(db.Model):
    __tablename__ = "project_members"
    __table_args__ = (db.UniqueConstraint("project_id", "user_id"),)
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.Enum(Role), nullable=False, default=Role.CONTRIBUTOR)
    assigned_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Milestone(db.Model):
    __tablename__ = "milestones"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="open")


class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    milestone_id = db.Column(db.Integer, db.ForeignKey("milestones.id"))
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.Enum(TaskStatus), nullable=False, default=TaskStatus.TODO)
    priority = db.Column(db.Enum(TaskPriority), nullable=False, default=TaskPriority.MEDIUM)
    due_date = db.Column(db.Date)
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="MAD")
    description = db.Column(db.Text)
    expense_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.Enum(ExpenseStatus), nullable=False, default=ExpenseStatus.VALID)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Attachment(db.Model):
    """A file attached to an expense (receipt, invoice). The file itself lives in storage under stored_name."""

    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)  # original name, for display and download
    stored_name = db.Column(db.String(64), unique=True, nullable=False)  # random; never user-controlled
    content_type = db.Column(db.String(100), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class TripStatus(str, enum.Enum):
    PLANNED = "planned"
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TripItemKind(str, enum.Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    CAR = "car"
    HOTEL = "hotel"
    MEETING = "meeting"
    OTHER = "other"


trip_travelers = db.Table(
    "trip_travelers",
    db.Column("trip_id", db.Integer, db.ForeignKey("trips.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


class Trip(db.Model):
    """Business travel for a project. Spend = valid expenses linked to the trip, in the project's currency."""

    __tablename__ = "trips"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    purpose = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum(TripStatus), nullable=False, default=TripStatus.PLANNED)
    budget = db.Column(db.Numeric(14, 2))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    travelers = db.relationship("User", secondary=trip_travelers, lazy="selectin")
    # Route for fuel estimates. Coordinates come from the map picker or the built-in city list.
    origin = db.Column(db.String(200))
    origin_lat = db.Column(db.Numeric(9, 6))
    origin_lng = db.Column(db.Numeric(9, 6))
    destination_lat = db.Column(db.Numeric(9, 6))
    destination_lng = db.Column(db.Numeric(9, 6))
    distance_km = db.Column(db.Numeric(9, 1))  # one way
    distance_source = db.Column(db.String(20))  # route (map directions) / straight_line / manual
    vehicle_type = db.Column(db.String(30))
    vehicle_count = db.Column(db.Integer, nullable=False, default=1)
    round_trip = db.Column(db.Boolean, nullable=False, default=True)
    fuel_city = db.Column(db.String(80))  # whose fuel price to use; defaults to the origin city


class FuelType(str, enum.Enum):
    PETROL = "petrol"
    DIESEL = "diesel"


class FuelPrice(db.Model):
    """Pump price per litre that the organization keeps up to date. city "" is the default for any city."""

    __tablename__ = "fuel_prices"
    __table_args__ = (db.UniqueConstraint("organization_id", "city", "fuel_type"),)
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    city = db.Column(db.String(80), nullable=False, default="")
    fuel_type = db.Column(db.Enum(FuelType), nullable=False)
    price_per_litre = db.Column(db.Numeric(8, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    as_of = db.Column(db.Date, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source = db.Column(db.String(20), nullable=False, default="manual")  # manual / openvan (teraedge: earlier)
    fetched_at = db.Column(db.DateTime(timezone=True))  # when an automatic source was read


class TripItem(db.Model):
    """One itinerary entry. Times are local to where they happen ("HH:MM"), so no timezone conversion."""

    __tablename__ = "trip_items"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    kind = db.Column(db.Enum(TripItemKind), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5))
    end_time = db.Column(db.String(5))
    location = db.Column(db.String(200))
    confirmation = db.Column(db.String(100))
    estimated_cost = db.Column(db.Numeric(14, 2))
    notes = db.Column(db.Text)


class MovementKind(str, enum.Enum):
    RECEIVE = "receive"  # stock in (delivery, purchase)
    ISSUE = "issue"  # stock out (used, optionally on a project)
    ADJUST = "adjust"  # manual correction (damage, loss, found)
    COUNT = "count"  # stock count: sets the quantity to what was counted
    TRANSFER = "transfer"  # between warehouses of the same inventory; the total doesn't change
    MOVE_OUT = "move_out"  # to another inventory (General stock <-> a project): leaves this item...
    MOVE_IN = "move_in"  # ...and arrives in the matching item of the other inventory


class Warehouse(db.Model):
    """A place where stock is kept: belongs to a project, or to General stock (project_id empty)."""

    __tablename__ = "warehouses"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(300))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class InventoryItem(db.Model):
    """Something the organization keeps in stock. Quantity changes only through InventoryMovement."""

    __tablename__ = "inventory_items"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    # The project whose inventory this item is in; empty for General stock (the organization's own).
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(60))
    unit = db.Column(db.String(20), nullable=False, default="pcs")
    unit_cost = db.Column(db.Numeric(14, 2))  # in the organization's default currency
    quantity_on_hand = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    reorder_level = db.Column(db.Numeric(12, 2))
    location = db.Column(db.String(120))
    description = db.Column(db.Text)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class InventoryStock(db.Model):
    """How much of an item is in one warehouse. What isn't in any warehouse is quantity_on_hand minus these."""

    __tablename__ = "inventory_stock"
    __table_args__ = (db.UniqueConstraint("item_id", "warehouse_id", name="uq_inventory_stock_item_warehouse"),)
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=0)


class InventoryMovement(db.Model):
    """Append-only stock history. quantity_after is the on-hand quantity once the movement applied."""

    __tablename__ = "inventory_movements"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    kind = db.Column(db.Enum(MovementKind), nullable=False)
    quantity_delta = db.Column(db.Numeric(12, 2), nullable=False)
    quantity_after = db.Column(db.Numeric(12, 2), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    # Where the stock went in or out (transfers: from here...), and for transfers where it went to.
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"))
    to_warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"))
    note = db.Column(db.String(500))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AIConversation(db.Model):
    __tablename__ = "ai_conversations"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class AIMessage(db.Model):
    __tablename__ = "ai_messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("ai_conversations.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # user / assistant
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class AIUsage(db.Model):
    """One row per assistant request: operational metadata only, never prompt or answer text."""

    __tablename__ = "ai_usage"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    tool_calls = db.Column(db.Integer, nullable=False, default=0)
    cost_usd = db.Column(db.Numeric(12, 6), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False)  # ok / error
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class Notification(db.Model):
    """An in-app message for one user. `link` is a frontend path, e.g. /app/projects/3."""

    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    kind = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500))
    link = db.Column(db.String(200))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    read_at = db.Column(db.DateTime(timezone=True))


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), index=True)
    # Set for project-level entries (the project itself, its tasks, expenses, milestones) for the activity view.
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.Integer)
    meta = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
