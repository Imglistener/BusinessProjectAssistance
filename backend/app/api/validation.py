from .errors import ApiError


def get_json_body() -> dict:
    from flask import request

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("invalid_body", "Request body must be a JSON object.", 400)
    return data


def require_str(data: dict, field: str, *, max_len: int = 255, min_len: int = 1) -> str:
    value = data.get(field)
    if not isinstance(value, str) or len(value.strip()) < min_len:
        raise ApiError("validation_error", f"'{field}' is required.", 400, {"field": field})
    value = value.strip()
    if len(value) > max_len:
        raise ApiError("validation_error", f"'{field}' is too long.", 400, {"field": field})
    return value
