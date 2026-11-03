"""Keeps automatically saved fuel prices fresh: checked when the server starts, then every hour.

Prices are re-read once they are a day old (FUEL_AUTO_SYNC_HOURS), only for organizations that already use the
automatic source (they have rows from it), and only those rows: prices someone typed in stay as they are.
A failed read waits FUEL_AUTO_SYNC_RETRY_HOURS before the next try, so a broken source isn't hammered.

The check runs in a background thread of the web server process, started by the first request (so CLI commands
such as `flask db upgrade` never start it). There is one server process (see docs/deployment.md), so one thread.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import Flask
from sqlalchemy import func

from ..extensions import db
from ..models import FuelPrice, Organization, OrganizationMember, Role
from . import fuel_sync
from .projects import org_today

CHECK_EVERY_SECONDS = 3600

_started = False
_lock = threading.Lock()
_last_failure: Optional[datetime] = None


def last_synced() -> Optional[datetime]:
    """When the automatic source was last read successfully, across organizations."""
    value = db.session.query(func.max(FuelPrice.fetched_at)).filter(FuelPrice.source == fuel_sync.SOURCE).scalar()
    if value is not None and value.tzinfo is None:  # SQLite drops the timezone
        value = value.replace(tzinfo=timezone.utc)
    return value


def synced_organizations() -> list[Organization]:
    ids = {row.organization_id for row in FuelPrice.query.filter_by(source=fuel_sync.SOURCE)}
    return Organization.query.filter(Organization.id.in_(ids), Organization.default_currency == "MAD").all() if ids else []


def is_due(now: datetime, max_age_hours: int, retry_hours: int) -> bool:
    if _last_failure is not None and now - _last_failure < timedelta(hours=retry_hours):
        return False
    last = last_synced()
    return last is None or now - last >= timedelta(hours=max_age_hours)


def run_if_due(app: Flask, now: Optional[datetime] = None) -> Optional[int]:
    """Update every organization that uses the automatic source, if due. Returns organizations updated, or None."""
    global _last_failure
    now = now or datetime.now(timezone.utc)
    cfg = app.config
    if not is_due(now, cfg["FUEL_AUTO_SYNC_HOURS"], cfg["FUEL_AUTO_SYNC_RETRY_HOURS"]):
        return None
    organizations = synced_organizations()
    if not organizations:
        return None
    try:
        snapshot = fuel_sync.fetch(force=True)
    except fuel_sync.FuelSyncError as e:
        _last_failure = now
        app.logger.warning("Automatic fuel price update failed: %s", e)
        return None
    _last_failure = None
    updated = 0
    for org in organizations:
        owner = OrganizationMember.query.filter_by(organization_id=org.id, role=Role.OWNER, status="active").first()
        if owner is None:
            continue
        fuel_sync.apply(org.id, owner.user_id, snapshot, org_today(org.timezone), keep_manual=True)
        updated += 1
    db.session.commit()
    app.logger.info("Fuel prices updated automatically for %d organization(s)", updated)
    return updated


def _loop(app: Flask) -> None:
    while True:
        with app.app_context():
            try:
                run_if_due(app)
            except Exception:  # never let the thread die; try again next hour
                db.session.rollback()
                app.logger.exception("Automatic fuel price update crashed")
            finally:
                db.session.remove()
        time.sleep(CHECK_EVERY_SECONDS)


def start(app: Flask) -> None:
    """Start the hourly check once per process (no-op when disabled)."""
    global _started
    if not app.config.get("FUEL_AUTO_SYNC") or _started:
        return
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app,), name="fuel-auto-sync", daemon=True).start()


def reset_for_tests() -> None:
    global _started, _last_failure
    _started = False
    _last_failure = None
