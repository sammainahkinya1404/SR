"""API tests against a real SQLite database: migrated once, copied fresh for every test."""

import shutil
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("template") / "template.db"
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "head")
    return path


@pytest.fixture
def db_url(migrated_template, tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    shutil.copy(migrated_template, path)
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    # Most tests open several businesses to check isolation; single-shop mode has its own test.
    monkeypatch.setenv("SINGLE_SHOP", "false")
    db.reset_engine()
    yield url
    db.reset_engine()


@pytest.fixture
def client(db_url):
    with TestClient(app) as c:
        yield c


def open_business(client: TestClient, name: str = "Duka") -> dict[str, str]:
    """Create a business and return the owner's auth headers."""
    resp = client.post("/businesses", json={"name": name, "owner_name": "Owner"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {"X-Business-Id": body["id"], "X-User-Id": body["owner_id"]}


def add_user(client: TestClient, owner: dict[str, str], role: str) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    resp = client.post("/users", headers=owner, json={"id": user_id, "name": role, "role": role})
    assert resp.status_code == 201, resp.text
    return {"X-Business-Id": owner["X-Business-Id"], "X-User-Id": user_id}
