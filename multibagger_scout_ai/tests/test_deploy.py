from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from streamlit.testing.v1 import AppTest

from database.models import Base
from frontend import common as C
from database.connection import make_session_factory

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_all_tables_compile_for_postgresql():  # DDL generation only: no Postgres server was available to run against
    for t in Base.metadata.sorted_tables:
        assert str(CreateTable(t).compile(dialect=postgresql.dialect()))
        for ix in t.indexes:
            assert str(CreateIndex(ix).compile(dialect=postgresql.dialect()))


def test_password_gate(tmp_path, monkeypatch):
    f = make_session_factory(f"sqlite:///{tmp_path / 'g.db'}")
    monkeypatch.setattr(C, "factory", lambda: f)
    monkeypatch.setattr(C, "scheduler", lambda: None)
    monkeypatch.setenv("APP_PASSWORD", "s3cret-pass")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception and not at.sidebar.radio  # nothing of the app is shown before login
    at.text_input(key="pw").set_value("wrong").run()
    assert any("Wrong password" in e.value for e in at.error) and not at.sidebar.radio
    at.text_input(key="pw").set_value("s3cret-pass").run()
    assert not at.exception and at.sidebar.radio(key="nav")


def test_no_password_means_open_app(tmp_path, monkeypatch):
    f = make_session_factory(f"sqlite:///{tmp_path / 'o.db'}")
    monkeypatch.setattr(C, "factory", lambda: f)
    monkeypatch.setattr(C, "scheduler", lambda: None)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception and at.sidebar.radio(key="nav")
