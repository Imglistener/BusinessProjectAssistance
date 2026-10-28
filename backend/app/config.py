import os
from decimal import Decimal


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://bpa:bpa@localhost:5432/bpa"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "MAD")

    AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "")
    AI_REQUEST_TIMEOUT_SECONDS = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "30"))
    AI_MONTHLY_COST_CAP_USD = Decimal(os.getenv("AI_MONTHLY_COST_CAP_USD", "10"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
