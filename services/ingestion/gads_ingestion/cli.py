from __future__ import annotations

import argparse
import json
from datetime import date

from gads.db import session_scope
from gads.logging import configure_logging

from gads_ingestion.jobs import enqueue_account_sync, run_account_sync
from gads_ingestion.reconcile import reconcile_account


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Google Ads ingestion commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync")
    sync.add_argument("--account", required=True)
    sync.add_argument("--mode", choices=["initial", "daily", "weekly", "history"], default="daily")
    sync.add_argument("--start")
    sync.add_argument("--end")
    sync.add_argument("--enqueue", action="store_true")

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--account", required=True)

    args = parser.parse_args()
    if args.command == "reconcile":
        with session_scope() as session:
            print(json.dumps(reconcile_account(session, args.account), indent=2))
        return
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    if args.enqueue:
        print(json.dumps({"jobs": enqueue_account_sync(args.account, args.mode, start, end)}, indent=2))
        return
    print(json.dumps({"sync_runs": run_account_sync(args.account, args.mode, start, end)}, indent=2))


if __name__ == "__main__":
    main()
