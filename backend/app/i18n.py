"""Translations for text the API sends to people: error messages, notifications, estimate notes, emails.

The English text is the key, as in the frontend. Code keeps writing plain English (f-strings included);
`translate()` runs at the edge (error handler, notification list, emails) and recognises formatted
messages by matching them against the catalog's templates, so "Only 3 pcs on hand." finds
"Only {quantity_on_hand} {unit} on hand.". Values caught by a placeholder are translated too when they
are catalog entries themselves (field names, fuel types, dates).

Anything without a translation is returned unchanged, in English.
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Optional

from .translations import ar, fr

LANGS = ("en", "fr", "ar")
CATALOGS: dict[str, dict[str, str]] = {"fr": fr.MESSAGES, "ar": ar.MESSAGES}
MONTHS: dict[str, list[str]] = {"fr": fr.MONTHS, "ar": ar.MONTHS}
_EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_HUMAN_DATE = re.compile(r"^(\d{1,2}) (" + "|".join(_EN_MONTHS) + r") (\d{4})$")


def normalize(lang: Optional[str]) -> str:
    """'fr-MA' -> 'fr'; anything unsupported -> 'en'."""
    code = (lang or "").strip().lower()[:2]
    return code if code in LANGS else "en"


def request_lang() -> str:
    """The language the client asked for (the app sends Accept-Language with the picked language)."""
    from flask import has_request_context, request

    if not has_request_context():
        return "en"
    header = request.headers.get("Accept-Language", "")
    return normalize(header.split(",")[0].split(";")[0])


def _fill(text: str, values: dict) -> str:
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)


def _(text: str, lang: str, **values) -> str:
    """Translate a template written in code, then fill it: _("Hi {name},", "fr", name="Salma")."""
    template = CATALOGS.get(lang, {}).get(text, text)
    return _fill(template, values)


@lru_cache(maxsize=None)
def _patterns(lang: str) -> list[tuple[re.Pattern, list[str], str]]:
    """Catalog templates as regexes, most literal text first so specific templates win over vague ones."""
    out = []
    for key, value in CATALOGS.get(lang, {}).items():
        names = _PLACEHOLDER.findall(key)
        if not names:
            continue
        parts = _PLACEHOLDER.split(key)
        regex = "".join(re.escape(p) if i % 2 == 0 else "(.+?)" for i, p in enumerate(parts))
        literal = sum(len(p) for p in parts[::2])
        out.append((literal, re.compile(f"^{regex}$", re.S), names, value))
    out.sort(key=lambda x: -x[0])
    return [(r, n, v) for _, r, n, v in out]


def human_date(d: date, lang: str = "en") -> str:
    """8 Nov 2026 / 8 nov. 2026 / 8 نونبر 2026."""
    months = MONTHS.get(lang, _EN_MONTHS)
    return f"{d.day} {months[d.month - 1]} {d.year}"


def translate(text: Optional[str], lang: str, _depth: int = 0) -> Optional[str]:
    if not text or lang == "en" or lang not in CATALOGS:
        return text
    catalog = CATALOGS[lang]
    if text in catalog:
        return catalog[text]
    m = _HUMAN_DATE.match(text)
    if m:
        return f"{m.group(1)} {MONTHS[lang][_EN_MONTHS.index(m.group(2))]} {m.group(3)}"
    if _depth > 2:
        return text
    for regex, names, value in _patterns(lang):
        match = regex.match(text)
        if match:
            values = {n: translate(v, lang, _depth + 1) for n, v in zip(names, match.groups())}
            return _fill(value, values)
    return text
