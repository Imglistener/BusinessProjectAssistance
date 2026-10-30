"""File storage for attachments. Local folder for now (UPLOAD_DIR); a cloud bucket can implement the same
three functions later. Files are addressed only by random names we generate, never by user input.
"""
from __future__ import annotations

import os
import re
import secrets
import unicodedata

from flask import current_app

STORED_NAME = re.compile(r"^[a-f0-9]{32}$")

# Accepted types, identified from the file's first bytes (the browser's claim and the extension aren't trusted).
SIGNATURES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)


def sniff(head: bytes) -> tuple[str, str] | None:
    """(content type, extension) for an accepted file, else None."""
    for magic, ctype, ext in SIGNATURES:
        if head.startswith(magic):
            return ctype, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def clean_filename(name: str | None, fallback_ext: str) -> str:
    """Display name only: last path part, no control characters, at most 255 characters."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in unicodedata.normalize("NFC", name) if unicodedata.category(ch)[0] != "C").strip()
    if not name or name in (".", ".."):
        name = f"receipt{fallback_ext}"
    return name[-255:]


def _dir() -> str:
    path = current_app.config["UPLOAD_DIR"]
    os.makedirs(path, exist_ok=True)
    return path


def _path(stored_name: str) -> str:
    if not STORED_NAME.match(stored_name):
        raise ValueError("invalid stored name")
    return os.path.join(_dir(), stored_name)


def save(data: bytes) -> str:
    stored_name = secrets.token_hex(16)
    with open(_path(stored_name), "xb") as f:  # "x": never overwrite
        f.write(data)
    return stored_name


def read(stored_name: str) -> bytes:
    with open(_path(stored_name), "rb") as f:
        return f.read()


def delete(stored_name: str) -> None:
    try:
        os.remove(_path(stored_name))
    except FileNotFoundError:
        pass
