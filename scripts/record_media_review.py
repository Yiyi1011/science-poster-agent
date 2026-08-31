"""Record explicit developer/user review without overwriting generated media or AI receipts."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import studio_store as store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("job")
    parser.add_argument("--issue", action="append", required=True)
    args = parser.parse_args()
    project = store.get_project(args.project)
    job = next(m for m in project["media"] if m["id"] == args.job)
    reviews = job.setdefault("human_reviews", [])
    reviews.append({"at": store.now(), "reviewer": "developer_visual_check", "status": "needs_changes", "issues": args.issue})
    store.save_media(args.project, job)
    print("Human review appended; original assets and AI checks preserved.")


if __name__ == "__main__": main()
