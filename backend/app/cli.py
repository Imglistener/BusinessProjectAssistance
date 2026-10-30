"""Developer commands. `flask --app wsgi demo-data` fills the database with a sample organization."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import click
from flask import current_app
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import (
    Expense,
    Milestone,
    Organization,
    OrganizationMember,
    Project,
    ProjectStatus,
    Role,
    Task,
    TaskPriority,
    TaskStatus,
    User,
    utcnow,
)
from .services.audit import log_action
from .services.projects import org_today

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"
TEAMMATE_EMAIL = "salma.demo@example.com"


@click.command("demo-data")
@click.option("--yes", is_flag=True, help="Allow writing to a non-SQLite database.")
def demo_data(yes: bool) -> None:
    """Create a demo login and a sample organization with projects, tasks, expenses and milestones."""
    url = current_app.config["SQLALCHEMY_DATABASE_URI"]
    if not url.startswith("sqlite") and not yes:
        raise click.ClickException(f"This adds sample data to {url.split('@')[-1]}. Re-run with --yes to confirm.")
    if User.query.filter_by(email=DEMO_EMAIL).first():
        click.echo(f"Demo data already exists. Log in as {DEMO_EMAIL} / {DEMO_PASSWORD}.")
        return

    owner = User(first_name="Yasmine", last_name="Alaoui", email=DEMO_EMAIL, password_hash=generate_password_hash(DEMO_PASSWORD))
    mate = User(
        first_name="Salma", last_name="Bennani", email=TEAMMATE_EMAIL, password_hash=generate_password_hash(DEMO_PASSWORD)
    )
    org = Organization(name="Atlas Studio", description="Demo organization", default_currency="MAD")
    db.session.add_all([owner, mate, org])
    db.session.flush()
    db.session.add_all(
        [
            OrganizationMember(organization_id=org.id, user_id=owner.id, role=Role.OWNER),
            OrganizationMember(organization_id=org.id, user_id=mate.id, role=Role.CONTRIBUTOR),
        ]
    )
    today = org_today(org.timezone)
    day = lambda n: today + timedelta(days=n)  # noqa: E731

    def project(name, description, budget, start, end, status=ProjectStatus.ACTIVE):
        p = Project(
            organization_id=org.id, owner_id=owner.id, name=name, description=description, status=status,
            budget=Decimal(budget), currency="MAD", start_date=start, end_date=end,
        )
        db.session.add(p)
        db.session.flush()
        log_action(organization_id=org.id, actor_id=owner.id, action="project.created", entity_type="project",
                   entity_id=p.id, meta={"name": name, "budget": budget, "currency": "MAD"})
        return p

    def expenses(p, rows):
        for category, amount, offset, note, by in rows:
            e = Expense(project_id=p.id, created_by=by.id, category=category, amount=Decimal(amount), currency="MAD",
                        description=note, expense_date=day(offset))
            db.session.add(e)
            db.session.flush()
            log_action(organization_id=org.id, actor_id=by.id, action="expense.created", entity_type="expense",
                       entity_id=e.id, meta={"project_id": p.id, "amount": amount, "currency": "MAD", "category": category})

    def milestone(p, title, offset, done=False):
        m = Milestone(project_id=p.id, title=title, due_date=day(offset), status="done" if done else "open")
        db.session.add(m)
        db.session.flush()
        return m

    def tasks(p, rows):
        for title, status, priority, offset, who, ms in rows:
            t = Task(project_id=p.id, title=title, status=status, priority=priority,
                     due_date=day(offset) if offset is not None else None,
                     assignee_id=who.id if who else None, milestone_id=ms.id if ms else None,
                     completed_at=utcnow() if status == TaskStatus.DONE else None)
            db.session.add(t)
            db.session.flush()
            log_action(organization_id=org.id, actor_id=owner.id, action="task.created", entity_type="task",
                       entity_id=t.id, meta={"project_id": p.id, "priority": priority.value, "assignee_id": t.assignee_id})

    S, P = TaskStatus, TaskPriority

    # Over budget: spending ran ahead of the plan.
    web = project("Website redesign", "New marketing site with booking form.", "45000.00", day(-75), day(20))
    expenses(web, [
        ("Design", "18500.00", -60, "Brand and UI design", owner),
        ("Software", "6200.00", -45, "CMS licence, 1 year", owner),
        ("Services", "14800.00", -30, "Front-end development, phase 1", owner),
        ("Marketing", "7900.00", -12, "Launch photography", mate),
        ("Software", "1200.00", -5, "Booking plugin", mate),
    ])
    beta = milestone(web, "Beta site live", -10, done=True)
    launch = milestone(web, "Public launch", 20)
    tasks(web, [
        ("Approve homepage design", S.DONE, P.HIGH, -40, owner, beta),
        ("Migrate blog posts", S.DONE, P.MEDIUM, -15, mate, beta),
        ("Booking form QA", S.IN_PROGRESS, P.HIGH, 5, mate, launch),
        ("Write launch announcement", S.TODO, P.MEDIUM, 15, owner, launch),
        ("Set up analytics", S.TODO, P.LOW, 18, None, launch),
    ])

    # Behind schedule: overdue work and a missed milestone.
    move = project("Office move to Casablanca", "Move the team to the new office in Maarif.", "60000.00", day(-40), day(10))
    expenses(move, [
        ("Services", "9500.00", -35, "Movers deposit", owner),
        ("Equipment", "21400.00", -20, "Desks and chairs", owner),
        ("Travel", "1850.50", -8, "Site visits", mate),
    ])
    keys = milestone(move, "Keys handed over", -3)
    tasks(move, [
        ("Sign the lease", S.DONE, P.HIGH, -30, owner, keys),
        ("Book internet installation", S.BLOCKED, P.HIGH, -6, mate, keys),
        ("Order meeting room screen", S.TODO, P.MEDIUM, -2, mate, None),
        ("Plan moving day", S.IN_PROGRESS, P.HIGH, 4, owner, None),
        ("Update address on invoices", S.TODO, P.LOW, 9, None, None),
    ])

    # On track: early stage, healthy budget.
    app_ = project("Mobile app MVP", "First version of the client app.", "120000.00", day(-14), day(120))
    expenses(app_, [
        ("Design", "8000.00", -10, "UX research", owner),
        ("Software", "2400.00", -3, "Developer accounts and tools", mate),
    ])
    proto = milestone(app_, "Clickable prototype", 21)
    tasks(app_, [
        ("Interview 8 customers", S.DONE, P.HIGH, -4, owner, proto),
        ("Draft user flows", S.IN_PROGRESS, P.MEDIUM, 7, mate, proto),
        ("Choose tech stack", S.TODO, P.MEDIUM, 12, owner, None),
        ("Prototype review", S.TODO, P.HIGH, 21, owner, proto),
    ])

    # Planned and archived ones so filters have something to show.
    project("Trade fair stand", "Stand for the autumn trade fair.", "25000.00", day(30), day(60), ProjectStatus.PLANNED)
    project("2025 rebrand", "Finished last year.", "30000.00", day(-400), day(-300), ProjectStatus.ARCHIVED)

    db.session.commit()
    click.echo("Demo data created.")
    click.echo(f"  Owner:       {DEMO_EMAIL} / {DEMO_PASSWORD}")
    click.echo(f"  Contributor: {TEAMMATE_EMAIL} / {DEMO_PASSWORD}")
