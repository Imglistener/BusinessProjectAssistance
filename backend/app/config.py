import os
from datetime import timedelta
from decimal import Decimal


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://bpa:bpa@localhost:5432/bpa"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # How long a login lasts. There are no refresh tokens yet, so the user logs in again after this.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_ACCESS_TOKEN_HOURS", "12")))
    # Comma-separated frontend origins allowed to call the API; "*" is fine for local development only.
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    # Number of reverse proxies in front of the app that set X-Forwarded-For / -Proto (0 = none).
    PROXY_FIX_X_FOR = int(os.getenv("PROXY_FIX_X_FOR", "0"))

    DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "MAD")

    # Email: "console" logs emails instead of sending them; "resend" sends through Resend.
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    # EMAIL_PROVIDER=gmail: send through a Gmail account with an App Password (no domain needed).
    GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL", "").strip()
    GOOGLE_APP_NAME = os.getenv("GOOGLE_APP_NAME", "").strip()
    GOOGLE_APP_PASSWORD = os.getenv("GOOGLE_APP_PASSWORD", "")
    # EMAIL_PROVIDER=smtp: any other SMTP service (Brevo, Zoho, Mailgun SMTP...). From address: EMAIL_FROM.
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    # Uploaded receipts. A local folder for now; back it up with the database (see docs/deployment.md).
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
    # Flask rejects bigger request bodies before they're read (413).
    MAX_CONTENT_LENGTH = (MAX_UPLOAD_MB + 1) * 1024 * 1024

    # Frontend address used in emailed links.
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173")

    AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    AI_MODEL = os.getenv("AI_MODEL") or "openai/gpt-oss-120b"
    AI_REQUEST_TIMEOUT_SECONDS = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "30"))
    AI_MONTHLY_COST_CAP_USD = Decimal(os.getenv("AI_MONTHLY_COST_CAP_USD", "10"))
    # USD per million tokens, used for the monthly cap. Check the provider's current price list.
    AI_INPUT_PRICE_PER_MTOK_USD = Decimal(os.getenv("AI_INPUT_PRICE_PER_MTOK_USD", "0.15"))
    AI_OUTPUT_PRICE_PER_MTOK_USD = Decimal(os.getenv("AI_OUTPUT_PRICE_PER_MTOK_USD", "0.75"))
    AI_MAX_TOOL_ROUNDS = int(os.getenv("AI_MAX_TOOL_ROUNDS", "5"))
    AI_REQUESTS_PER_MINUTE = int(os.getenv("AI_REQUESTS_PER_MINUTE", "10"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key-that-is-long-enough-123"
    JWT_SECRET_KEY = "test-jwt-secret-key-that-is-long-enough-456"
    GROQ_API_KEY = ""  # tests never reach a real provider
    EMAIL_PROVIDER = "console"
    RESEND_API_KEY = ""
    GOOGLE_APP_PASSWORD = ""
    SMTP_PASSWORD = ""
    UPLOAD_DIR = ""  # set per test to a temporary folder
