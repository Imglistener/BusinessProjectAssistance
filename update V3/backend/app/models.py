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
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


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
    receipt_url = db.Column(db.String(500))  # attachments are "later"; kept nullable
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Resource(db.Model):
    __tablename__ = "resources"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(60))
    unit_cost = db.Column(db.Numeric(14, 2))
    description = db.Column(db.Text)


class ProjectResource(db.Model):
    __tablename__ = "project_resources"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False)
    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=1)
    total_cost = db.Column(db.Numeric(14, 2))


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


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.Integer)
    meta = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
