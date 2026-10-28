from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt, migrate


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    from . import models  # noqa: F401  (register models for migrations)
    from .api import api_bp

    app.register_blueprint(api_bp, url_prefix="/api")

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
