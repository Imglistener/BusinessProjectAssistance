"""One-time link tokens (invites, password resets). Only the SHA-256 hash is ever stored."""
import hashlib
import secrets
from datetime import timezone


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def aware(dt):
    """SQLite hands back naive datetimes; everything is stored in UTC."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)
