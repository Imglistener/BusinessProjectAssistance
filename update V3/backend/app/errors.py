class ApiError(Exception):
    """Raised anywhere in the backend; rendered as {"error": {...}} JSON by the API layer."""

    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details
