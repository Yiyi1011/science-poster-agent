"""Rebuild a completed media manifest from SQLite and independently verify its files.

No model calls. The stale canonical manifest is preserved once before replacement.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import studio_store as store
from app.services.studio_media import directory
from app.services.studio_video import verify_media_output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("job")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    project = store.get_project(args.project)
    job = next(item for item in project["media"] if item["id"] == args.job)
    if job.get("state") != "succeeded" or not job.get("video") or not job.get("subtitles"):
        raise SystemExit("Only a completed media job with video and subtitles can be refreshed")
    folder = directory(args.project, args.job)
    integrity = verify_media_output(folder, job["video"], job["subtitles"])
    if integrity["status"] != "ok":
        raise SystemExit("Media verification failed; canonical manifest was not replaced")
    canonical = folder / "manifest.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if canonical.is_file():
        backup = folder / f"manifest-before-refresh-{stamp}.json"
        shutil.copy2(canonical, backup)
        job.setdefault("files", []).append(backup.name)
    job["media_integrity_check"] = integrity
    job.setdefault("manifest_revisions", []).append({"at": store.now(), "reason": args.reason,
                                                       "paid_calls": 0})
    for name in ["manifest.json", *integrity.get("sample_frames", [])]:
        if name not in job.setdefault("files", []):
            job["files"].append(name)
    canonical.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    store.save_media(args.project, job)
    print(json.dumps({"project": args.project, "job": args.job, "state": job["state"],
                      "video": job["video"], "integrity": integrity, "paid_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
