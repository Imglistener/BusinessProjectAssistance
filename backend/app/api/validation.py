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
    "category": "Category",
    "amount": "Amount",
    "expense_date": "Date",
    "title": "Title",
    "priority": "Priority",
    "due_date": "Due date",
    "assignee_id": "Assignee",
    "milestone_id": "Milestone",
    "default_currency": "Currency",
    "quantity": "Quantity",
    "destination": "Destination",
    "estimated_cost": "Estimated cost",
    "date": "Date",
    "trip_id": "Trip",
    "counted": "Counted quantity",
    "unit_cost": "Unit cost",
    "reorder_level": "Reorder level",
    "unit": "Unit",
    "sku": "SKU",
    "location": "Location",
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


def parse_money(
    data: dict, field: str, *, required: bool = True, positive: bool = False
) -> Optional[Decimal]:
    """Amount with at most 2 decimals. Accepts a JSON number or numeric string.

    Non-negative by default; `positive=True` also rejects zero (expenses).
    """
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
    if positive and amount == 0:
        raise _bad(field, f"{_label(field)} must be more than zero.")
    if amount > MAX_MONEY:
        raise _bad(field, f"{_label(field)} is too large.")
    if amount != amount.quantize(Decimal("0.01")):
        raise _bad(field, f"{_label(field)} can have at most 2 decimal places.")
    return amount.quantize(Decimal("0.01"))


def parse_date(data: dict, field: str, *, required: bool = False) -> Optional[date]:
    value = data.get(field)
    if value is None or value == "":
        if required:
            raise _bad(field, f"{_label(field)} is required.")
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


def parse_enum(data: dict, field: str, enum_cls, default=None):
    """Return the enum member for data[field]; `default` when the field is absent or null."""
    raw = data.get(field)
    if raw is None:
        return default
    try:
        return enum_cls(raw)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)
        raise _bad(field, f"{_label(field)} must be one of: {allowed}.")


def parse_optional_id(data: dict, field: str) -> Optional[int]:
    value = data.get(field)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _bad(field, f"{_label(field)} is not valid.")
    return value


MAX_QUANTITY = Decimal("9999999999.99")  # fits Numeric(12, 2)


def parse_quantity(data: dict, field: str, *, required: bool = True, positive: bool = False) -> Optional[Decimal]:
    """A stock quantity with at most 2 decimals (e.g. 12 or 2.5 kg). Non-negative; `positive` also rejects 0."""
    value = data.get(field)
    if value is None or value == "":
        if required:
            raise _bad(field, f"{_label(field)} is required.")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _bad(field, f"{_label(field)} must be a number, like 12 or 2.5.")
    try:
        qty = Decimal(str(value).strip())
    except InvalidOperation:
        raise _bad(field, f"{_label(field)} must be a number, like 12 or 2.5.")
    if not qty.is_finite():
        raise _bad(field, f"{_label(field)} must be a number, like 12 or 2.5.")
    if qty < 0:
        raise _bad(field, f"{_label(field)} can't be negative.")
    if positive and qty == 0:
        raise _bad(field, f"{_label(field)} must be more than zero.")
    if qty > MAX_QUANTITY:
        raise _bad(field, f"{_label(field)} is too large.")
    if qty != qty.quantize(Decimal("0.01")):
        raise _bad(field, f"{_label(field)} can have at most 2 decimal places.")
    return qty.quantize(Decimal("0.01"))


def parse_signed_quantity(data: dict, field: str) -> Decimal:
    """A non-zero quantity that may be negative, e.g. "-3" for three damaged units."""
    raw = data.get(field)
    negative = (isinstance(raw, str) and raw.strip().startswith("-")) or (
        isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw < 0
    )
    if negative:
        raw = raw.strip()[1:] if isinstance(raw, str) else -raw
    magnitude = parse_quantity({field: raw}, field, positive=True)
    return -magnitude if negative else magnitude
