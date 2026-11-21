"""Run one supervised automation cycle (probe -> pipeline -> digest -> notify). Used by Windows Task Scheduler and GitHub Actions.
Exit code 0 = complete or partial; 1 = nothing useful happened (provider down or pipeline failed), so the scheduler flags the run."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import init_db  # noqa: E402
from services.automation_agent import exit_code, run_cycle  # noqa: E402
from services.serialization import to_jsonable  # noqa: E402


def main():
    init_db()
    cycle = run_cycle()
    print(json.dumps(to_jsonable(cycle), indent=2, default=str))
    return exit_code(cycle)


if __name__ == "__main__":
    sys.exit(main())
