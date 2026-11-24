"""Which AI providers can be used now, and which one answers a question.

A provider whose usage limit ran out is set aside until it resets (kept in the database, so restarts don't
forget it). Everyone shares it: the limits belong to the app's keys, not to a person.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from ..errors import ApiError
from ..extensions import db
from ..models import AIProviderStatus
from . import ai_provider
from .ai_provider import ProviderRateLimited

# Used when the provider doesn't say when its limit resets.
DEFAULT_RESET_SECONDS = 60
# With every provider exhausted, one that resets this soon is worth waiting for; otherwise say so at once.
WORTH_WAITING_SECONDS = ai_provider.MAX_RETRY_WAIT_SECONDS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value  # SQLite drops the timezone


def _gemini_daily_reset(now: datetime) -> datetime:
    """Gemini's daily quotas reset at midnight Pacific time."""
    pacific = ZoneInfo("America/Los_Angeles")
    tomorrow = now.astimezone(pacific).date() + timedelta(days=1)
    return datetime.combine(tomorrow, time(0), tzinfo=pacific).astimezone(timezone.utc)


def _statuses(now: datetime) -> dict[str, AIProviderStatus]:
    return {s.provider: s for s in AIProviderStatus.query.all() if _aware(s.exhausted_until) > now}


def mark_exhausted(name: str, error: ProviderRateLimited, now: Optional[datetime] = None) -> None:
    """Commits."""
    now = now or _now()
    if error.daily and name == "gemini":
        until = _gemini_daily_reset(now)  # its RetryInfo gives seconds even for a daily quota
    elif error.retry_after is not None:
        until = now + timedelta(seconds=error.retry_after)
    else:
        until = now + timedelta(days=1) if error.daily else now + timedelta(seconds=DEFAULT_RESET_SECONDS)
    db.session.merge(AIProviderStatus(provider=name, exhausted_until=until, daily=error.daily))
    db.session.commit()


def overview(now: Optional[datetime] = None) -> list[dict]:
    """For the picker: every configured provider, the default first."""
    exhausted = _statuses(now or _now())
    return [
        {
            "id": name,
            "label": ai_provider.LABELS[name],
            "model": ai_provider.model_for(name),
            "available": name not in exhausted,
            "available_at": _aware(exhausted[name].exhausted_until).isoformat() if name in exhausted else None,
            "daily": exhausted[name].daily if name in exhausted else False,
        }
        for name in ai_provider.configured_providers()
    ]


def candidates(wanted: Optional[str], now: Optional[datetime] = None) -> tuple[list[str], list[str]]:
    """(providers to try in order, configured providers). The wanted one (or the default) comes first if it's usable.

    The first list is empty when all are exhausted and none resets soon.
    """
    if wanted is not None and wanted not in tuple(ai_provider.LABELS):
        raise ApiError("validation_error", "Choose one of the available AI models.", 400, {"field": "provider"})
    now = now or _now()
    names = sorted(ai_provider.configured_providers(), key=lambda n: n != wanted)
    exhausted = _statuses(now)
    usable = [n for n in names if n not in exhausted]
    if usable or not names:
        return usable, names
    soonest = min(names, key=lambda n: _aware(exhausted[n].exhausted_until))
    wait = (_aware(exhausted[soonest].exhausted_until) - now).total_seconds()
    return ([soonest] if wait <= WORTH_WAITING_SECONDS else []), names


def back_at(names: list[str], now: Optional[datetime] = None) -> Optional[datetime]:
    """When the first of these providers is usable again; None if one already is."""
    now = now or _now()
    exhausted = _statuses(now)
    if not names or any(n not in exhausted for n in names):
        return None
    return min(_aware(exhausted[n].exhausted_until) for n in names)
