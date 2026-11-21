from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from config import settings
from database.models import Base, SchemaMigration

SCHEMA_VERSION = 1  # bump + add a step in database/migrations when models change
_factory = None


def make_session_factory(url=None):
    url = url or settings.DATABASE_URL
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # enforce foreign keys in SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, future=True)() as s:
        if not s.get(SchemaMigration, SCHEMA_VERSION):
            s.add(SchemaMigration(version=SCHEMA_VERSION))
            s.commit()
    return sessionmaker(engine, expire_on_commit=False, future=True)


def init_db(url=None):
    global _factory
    _factory = make_session_factory(url)
    return _factory


def get_factory():
    return _factory or init_db()


@contextmanager
def session_scope(factory=None):
    s = (factory or get_factory())()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
