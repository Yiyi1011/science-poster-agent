"""Explicit paid media verification on one existing, source-reviewed project."""
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import studio_store as store
from app.services.studio_media import execute_media
from app.studio_models import MediaInput


async def main(project_id):
    p = store.get_project(project_id)
    request = MediaInput(request_id=uuid4(), expected_version=p["versions"][-1]["version"])
    store.reserve_media(project_id, request)
    print(json.dumps({"project": project_id, "job": str(request.request_id)}), flush=True)
    task = asyncio.create_task(execute_media(project_id, request))
    stage = ""
    while not task.done():
        job = next(m for m in store.get_project(project_id)["media"] if m["id"] == str(request.request_id))
        if stage != job["stage"]:
            stage = job["stage"]; print(stage, flush=True)
        await asyncio.wait([task], timeout=5)
    await task
    job = next(m for m in store.get_project(project_id)["media"] if m["id"] == str(request.request_id))
    print(json.dumps(job, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("Usage: verify_studio_media.py PROJECT_UUID")
    asyncio.run(main(sys.argv[1]))
