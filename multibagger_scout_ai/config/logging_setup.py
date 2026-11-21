import logging
from logging.handlers import RotatingFileHandler

from config import settings

_done = False


def setup_logging():
    global _done
    if _done:
        return
    (settings.ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(settings.ROOT / "logs" / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    _done = True
