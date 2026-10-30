from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import cors, db, jwt, migrate


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    if app.config["PROXY_FIX_X_FOR"]:
        n = app.config["PROXY_FIX_X_FOR"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n)
    _warn_about_weak_secrets(app)

    from . import models  # noqa: F401  (register models for migrations)
    from .api import api_bp

    app.register_blueprint(api_bp, url_prefix="/api")

    from .ai_eval import ai_eval
    from .cli import demo_data

    app.cli.add_command(demo_data)
    app.cli.add_command(ai_eval)

    # Consistent JSON errors for JWT problems.
    def _jwt_error(code, message):
        return jsonify(error={"code": code, "message": message}), 401

    jwt.unauthorized_loader(lambda reason: _jwt_error("unauthorized", "Authentication required."))
    jwt.invalid_token_loader(lambda reason: _jwt_error("invalid_token", "Invalid token."))
    jwt.expired_token_loader(lambda header, payload: _jwt_error("token_expired", "Token expired."))

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(error={"code": "not_found", "message": "Resource not found."}), 404

    @app.errorhandler(500)
    def server_error(_e):
        # Never expose stack traces or internals (FR-18).
        return jsonify(error={"code": "server_error", "message": "Unexpected error."}), 500

    return app


WEAK_SECRETS = {"dev-secret", "dev-jwt-secret", "change-me", "change-me-too"}


def _warn_about_weak_secrets(app: Flask) -> None:
    """Placeholder or short secrets let anyone forge login tokens. Loud warning, not a crash, for local use."""
    for name in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = app.config.get(name) or ""
        if value in WEAK_SECRETS or len(value) < 32:
            app.logger.warning(
                "%s is a placeholder or shorter than 32 characters. Set a long random value before deploying "
                "(python -c \"import secrets; print(secrets.token_urlsafe(48))\").",
                name,
            )
