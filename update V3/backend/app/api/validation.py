from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from ..errors import ApiError

MAX_MONEY = Decimal("999999999999.99")  # fits Numeric(14, 2)


def get_json_body() -> dict:
    from flask import request

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("invalid_body", "Request body must be a JSON object.", 400)
    return data


# Messages are shown to people, so refer to fields by their on-screen names.
FIELD_LABELS = {
    "name": "Project name",
    "first_name": "First name",
    "last_name": "Last name",
    "budget": "Budget",
    "currency": "Currency",
    "start_date": "Start date",
    "end_date": "End date",
    "default_currency": "Currency",
}


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").capitalize())


def _bad(field: str, message: str) -> ApiError:
    return ApiError("validation_error", message, 400, {"field": field})


def require_str(data: dict, field: str, *, max_len: int = 255, min_len: int = 1) -> str:
    value = data.get(field)
    if not isinstance(value, str) or len(value.strip()) < min_len:
        raise _bad(field, f"{_label(field)} is required.")
    value = value.strip()
    if len(value) > max_len:
        raise _bad(field, f"{_label(field)} is too long.")
    return value


def optional_str(data: dict, field: str, *, max_len: int = 255) -> Optional[str]:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _bad(field, f"{_label(field)} must be text.")
    value = value.strip()
    if len(value) > max_len:
        raise _bad(field, f"{_label(field)} is too long.")
    return value or None


def parse_money(data: dict, field: str, *, required: bool = True) -> Optional[Decimal]:
    """Non-negative amount with at most 2 decimals. Accepts a JSON number or numeric string."""
    value = data.get(field)
    if value is None or value == "":
        if required:
            raise _bad(field, f"{_label(field)} is required.")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _bad(field, f"{_label(field)} must be an amount, like 1500 or 1500.50.")
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        raise _bad(field, f"{_label(field)} must be an amount, like 1500 or 1500.50.")
    if not amount.is_finite():
        raise _bad(field, f"{_label(field)} must be an amount, like 1500 or 1500.50.")
    if amount < 0:
        raise _bad(field, f"{_label(field)} can't be negative.")
    if amount > MAX_MONEY:
        raise _bad(field, f"{_label(field)} is too large.")
    if amount != amount.quantize(Decimal("0.01")):
        raise _bad(field, f"{_label(field)} can have at most 2 decimal places.")
    return amount.quantize(Decimal("0.01"))


def parse_date(data: dict, field: str) -> Optional[date]:
    value = data.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _bad(field, f"{_label(field)} must be a valid date.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _bad(field, f"{_label(field)} must be a valid date.")


def parse_currency(data: dict, field: str, default: str) -> str:
    value = data.get(field)
    if value is None or value == "":
        return default
    if not isinstance(value, str) or len(value.strip()) != 3 or not value.strip().isalpha():
        raise _bad(field, f"{_label(field)} must be a 3-letter code, like MAD.")
    return value.strip().upper()
