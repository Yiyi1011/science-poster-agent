"""Archive or restore saved Studio projects without deleting their data.

Archived projects disappear from the normal selector, while versions, evidence and
media remain in SQLite/artifacts and can be restored by ID.  No model calls.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import studio_store as store


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--archive", nargs="+")
    action.add_argument("--restore", nargs="+")
    action.add_argument("--list", action="store_true")
    parser.add_argument("--reason", default="duplicate project hidden from normal selector")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    changed = []
    if args.archive:
        for project_id in args.archive:
            project = store.get_project(project_id)
            store.archive_project(project_id, args.reason)
            changed.append({"action": "archived", "id": project_id, "topic": project["input"]["topic"]})
    elif args.restore:
        for project_id in args.restore:
            project = store.get_project(project_id)
            store.restore_project(project_id)
            changed.append({"action": "restored", "id": project_id, "topic": project["input"]["topic"]})

    result = {"at": datetime.now().astimezone().isoformat(), "reason": args.reason,
              "changed": changed, "archived": store.list_archived_projects(), "paid_calls": 0}
    if args.receipt:
        target = args.receipt.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["receipt"] = str(target)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
