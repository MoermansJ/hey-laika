"""One-off migration for the behavior run log (AGENT-03).

Adds the agent-outcome columns (``outcome``, ``sensor_delta``) and the
partial outcome index to an existing ``framework_behavior_runs`` table in
place. The adapter also runs this automatically on startup
(``BehaviorStore.init``); this entry point exists for migrating a database
file without starting the adapter. Safe to run repeatedly.

    cd dog && python -m app.migrate_run_log
"""
from app.behavior_store import migrate_run_log
from app.models import Base, engine


def main() -> int:
    # A database that predates the behavior framework has no run table yet;
    # create_all makes it with the current schema (a no-op otherwise).
    Base.metadata.create_all(engine)
    added = migrate_run_log(engine)
    print("framework_behavior_runs: added " + (", ".join(added) if added
                                               else "nothing (up to date)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
