from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def utc_naive():
    """SQLite stores naive datetimes; we always store and compare UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
