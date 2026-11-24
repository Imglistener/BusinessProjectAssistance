"""Saved assistant conversations: private to their author, kept AI_CONVERSATION_RETENTION_DAYS after the last message.

Only the text of the questions and answers is kept, plus how many draft cards an answer showed. The drafts
themselves are not: one brought back from history could be confirmed a second time.

Old conversations are removed by a background thread (hourly, started by the web server's first request, like
the fuel price check) and by `flask ai-purge-conversations`.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import click
from flask import Flask, current_app
from flask.cli import with_appcontext

from ..errors import ApiError
from ..extensions import db
from ..models import AIConversation, AIMessage, Project, utcnow

TITLE_CHARS = 80
LIST_LIMIT = 100
# Turns sent to the model as context: the same window the browser used to send.
HISTORY_TURNS = 12
CHECK_EVERY_SECONDS = 3600

_started = False
_lock = threading.Lock()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value  # SQLite drops the timezone


def _title(question: str) -> str:
    text = re.sub(r"\s+", " ", question).strip()
    return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1].rstrip() + "…"


def get_owned(user_id: int, organization_id: int, conversation_id: int) -> AIConversation:
    """The user's own conversation in this organization; anyone else's is "not found"."""
    conv = db.session.get(AIConversation, conversation_id)
    if conv is None or conv.user_id != user_id or conv.organization_id != organization_id:
        raise ApiError("conversation_not_found", "Conversation not found.", 404)
    return conv


def _messages(conv: AIConversation) -> list[AIMessage]:
    return AIMessage.query.filter_by(conversation_id=conv.id).order_by(AIMessage.id).all()


def history(conv: AIConversation) -> list[dict]:
    """The latest turns, oldest first, in the format the chat expects."""
    rows = (
        AIMessage.query.filter_by(conversation_id=conv.id).order_by(AIMessage.id.desc()).limit(HISTORY_TURNS).all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def record(
    conversation_id: Optional[int],
    user_id: int,
    organization_id: int,
    project_id: Optional[int],
    question: str,
    reply: dict,
) -> AIConversation:
    """Save one question and its answer, starting a conversation if needed. Commits.

    An answer can take a while: if the conversation or project was deleted meanwhile (another tab, another user),
    the turn is still saved, in a new conversation or without the project.
    """
    now = utcnow()
    conv = db.session.get(AIConversation, conversation_id, populate_existing=True) if conversation_id else None
    if project_id is not None and db.session.get(Project, project_id, populate_existing=True) is None:
        project_id = None
    if conv is None:
        conv = AIConversation(
            user_id=user_id, organization_id=organization_id, title=_title(question), created_at=now, updated_at=now
        )
        db.session.add(conv)
        db.session.flush()
    conv.project_id = project_id
    conv.updated_at = now
    drafts = sum(len(reply.get(k) or []) for k in ("proposals", "stock_proposals", "action_proposals"))
    db.session.add(AIMessage(conversation_id=conv.id, role="user", content=question.strip(), created_at=now))
    db.session.add(AIMessage(conversation_id=conv.id, role="assistant", content=reply["answer"], drafts=drafts, created_at=now))
    db.session.commit()
    return conv


def summary(conv: AIConversation) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "project_id": conv.project_id,
        "created_at": _aware(conv.created_at).isoformat(),
        "updated_at": _aware(conv.updated_at).isoformat(),
    }


def detail(conv: AIConversation) -> dict:
    return {
        **summary(conv),
        "messages": [
            {"role": m.role, "content": m.content, "drafts": m.drafts, "created_at": _aware(m.created_at).isoformat()}
            for m in _messages(conv)
        ],
    }


def list_for(user_id: int, organization_id: int) -> list[AIConversation]:
    return (
        AIConversation.query.filter_by(user_id=user_id, organization_id=organization_id)
        .order_by(AIConversation.updated_at.desc(), AIConversation.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )


def _delete_ids(ids: list[int]) -> int:
    if not ids:
        return 0
    gone = dict(synchronize_session=False)
    AIMessage.query.filter(AIMessage.conversation_id.in_(ids)).delete(**gone)
    AIConversation.query.filter(AIConversation.id.in_(ids)).delete(**gone)
    return len(ids)


def delete(conv: AIConversation) -> None:
    """In the current transaction."""
    _delete_ids([conv.id])


def delete_for(user_id: int, organization_id: int) -> int:
    """All of one person's conversations in one organization, in the current transaction."""
    ids = [c for (c,) in db.session.query(AIConversation.id).filter_by(user_id=user_id, organization_id=organization_id)]
    return _delete_ids(ids)


def purge_expired(now: Optional[datetime] = None, days: Optional[int] = None) -> int:
    """Delete conversations with no message for `days` (AI_CONVERSATION_RETENTION_DAYS). Commits."""
    now = now or datetime.now(timezone.utc)
    days = days or current_app.config["AI_CONVERSATION_RETENTION_DAYS"]
    cutoff = now - timedelta(days=days)
    ids = [c for (c,) in db.session.query(AIConversation.id).filter(AIConversation.updated_at < cutoff)]
    count = _delete_ids(ids)
    db.session.commit()
    return count


def _loop(app: Flask) -> None:
    while True:
        with app.app_context():
            try:
                count = purge_expired()
                if count:
                    app.logger.info("Deleted %d expired assistant conversation(s)", count)
            except Exception:  # never let the thread die; try again next hour
                db.session.rollback()
                app.logger.exception("Assistant conversation clean-up crashed")
            finally:
                db.session.remove()
        time.sleep(CHECK_EVERY_SECONDS)


def start(app: Flask) -> None:
    """Start the hourly clean-up once per process (not under tests)."""
    global _started
    if app.config.get("TESTING") or _started:
        return
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app,), name="ai-conversation-retention", daemon=True).start()


@click.command("ai-purge-conversations")
@with_appcontext
def ai_purge_conversations():
    """Delete assistant conversations older than AI_CONVERSATION_RETENTION_DAYS."""
    count = purge_expired()
    click.echo(f"Deleted {count} conversation(s) with no activity in {current_app.config['AI_CONVERSATION_RETENTION_DAYS']} days.")
