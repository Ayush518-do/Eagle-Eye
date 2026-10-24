from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.db import get_db, get_session_factory
from backend.app.models import Cabinet


def make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_session_factory] = lambda: session_factory

    @app.post("/c/{cid}")
    def create(cid: str, commit: bool = True, db: Session = Depends(get_db)):
        db.add(Cabinet(id=cid, name="n"))
        if commit:
            db.commit()
        return {"ok": True}

    @app.get("/c")
    def list_all(db: Session = Depends(get_db)):
        return [c.id for c in db.scalars(select(Cabinet).order_by(Cabinet.id))]

    return app


def test_session_dependency_uses_the_overridden_database(session_factory):
    client = TestClient(make_app(session_factory))
    assert client.post("/c/CAB-001").status_code == 200
    assert client.get("/c").json() == ["CAB-001"]
    with session_factory() as s:  # a separate session sees it, so it was really committed
        assert s.get(Cabinet, "CAB-001") is not None


def test_uncommitted_work_is_not_saved(session_factory):
    client = TestClient(make_app(session_factory))
    client.post("/c/CAB-002?commit=false")
    assert client.get("/c").json() == []


def test_default_factory_follows_settings_database_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'x.db').as_posix()}"
    factory = get_session_factory(Settings(_env_file=None, database_url=url))
    assert factory.kw["bind"].url.database == (tmp_path / "x.db").as_posix()
    assert get_session_factory(Settings(_env_file=None, database_url=url)) is factory  # cached per URL
