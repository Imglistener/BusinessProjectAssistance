import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


@pytest.fixture()
def app(tmp_path):
    app = create_app(TestConfig)
    app.config["UPLOAD_DIR"] = str(tmp_path / "uploads")
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
