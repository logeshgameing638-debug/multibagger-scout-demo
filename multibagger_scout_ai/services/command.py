"""Floor 00 Central Command helpers: DB health, backup, log tail, data-source health."""
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, text

from config import settings
from database.connection import session_scope
from database.models import Base, DataQualityLog, DataSource


def _sqlite_path():
    url = settings.DATABASE_URL
    return Path(url.replace("sqlite:///", "", 1)) if url.startswith("sqlite:///") else None


def db_health(factory=None):
    with session_scope(factory) as s:
        out = {"tables": {}, "ok": True, "integrity": None}
        for t in Base.metadata.sorted_tables:
            out["tables"][t.name] = s.execute(func.count().select().select_from(t)).scalar()
        if s.get_bind().dialect.name == "sqlite":
            out["integrity"] = s.execute(text("PRAGMA integrity_check")).scalar()
            out["ok"] = out["integrity"] == "ok"
    p = _sqlite_path()
    out["size_mb"] = round(p.stat().st_size / 1e6, 2) if p and p.exists() else None
    return out


def backup_database(dest_dir=None):
    """Consistent copy using SQLite's online backup API (safe while the app runs)."""
    src = _sqlite_path()
    if src is None or not src.exists():
        raise FileNotFoundError("no SQLite database file to back up")
    dest = Path(dest_dir or settings.ROOT / "backups")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"scout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    with sqlite3.connect(src) as a, sqlite3.connect(target) as b:
        a.backup(b)
    return target


def tail_log(n=80):
    p = settings.ROOT / "logs" / "app.log"
    return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:] if p.exists() else []


def source_health(factory=None):
    with session_scope(factory) as s:
        return [{"source": d.name, "last_success": d.last_success_at, "last_error": d.last_error, "last_error_at": d.last_error_at, "note": d.description}
                for d in s.query(DataSource)]
