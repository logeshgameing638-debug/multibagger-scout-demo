"""Local APScheduler for the existing daily pipeline. It fires only while this process AND the computer are running.
Enable/disable and time come from the existing app settings (scheduler_enabled, schedule_time)."""
import logging
from datetime import timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services import settings_store

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
JOB_ID = "daily_pipeline"


def _run(factory=None):
    from services.automation_agent import run_cycle
    try:
        run_cycle(factory=factory)
    except Exception:  # the scheduler thread must survive a failed run
        log.exception("scheduled automation cycle failed")


def build_scheduler(factory=None, job=None):
    hh, mm = (int(x) for x in settings_store.get("schedule_time", factory).split(":"))
    sch = BackgroundScheduler(timezone=IST)
    sch.add_job(job or (lambda: _run(factory)), CronTrigger(day_of_week="mon-fri", hour=hh, minute=mm, timezone=IST), id=JOB_ID,
                max_instances=1, coalesce=True, misfire_grace_time=3600, replace_existing=True)
    return sch


def start_if_enabled(factory=None):
    if not settings_store.get_bool("scheduler_enabled", factory):
        return None
    sch = build_scheduler(factory)
    sch.start()
    return sch


def next_run(sch):
    job = sch.get_job(JOB_ID) if sch else None
    return getattr(job, "next_run_time", None)
