"""Milestone-1 acceptance driver: create a studio project and run the full
closed loop (research -> generation -> review -> cartoon -> TTS -> MP4) against
the locally running backend with real Bailian Qwen. Records stages and usage.

Usage: PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe scripts/run_studio_acceptance.py "<问题>"
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

API = "http://127.0.0.1:8000/api/studio"
POLL_SECONDS = 12
TIMEOUT_SECONDS = 90 * 60


def post(client: httpx.Client, path: str, payload: dict) -> dict:
    response = client.post(API + path, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def main() -> None:
    topic = sys.argv[1] if len(sys.argv) > 1 else "为什么月亮会有圆缺变化？"
    client = httpx.Client()
    project = post(client, "/projects", {"topic": topic, "audience": "普通公众", "auto_sources": True})
    project_id = project["id"]
    print(f"created project {project_id} topic={topic!r}", flush=True)
    run = post(client, f"/projects/{project_id}/run",
               {"request_id": str(uuid4()), "expected_version": 0, "make_video": True})
    print("run accepted; polling…", flush=True)
    deadline = time.time() + TIMEOUT_SECONDS
    last_run_state = last_media_state = ""
    while time.time() < deadline:
        detail = client.get(f"{API}/projects/{project_id}", timeout=60).json()
        run_state = (detail.get("runs") or [{}])[-1].get("state", "")
        media = [m for m in detail.get("media", []) if m.get("state") == "running"]
        media_state = media[0].get("stage", "") if media else (detail.get("media") or [{}])[-1].get("state", "")
        if run_state != last_run_state or media_state != last_media_state:
            print(f"[{time.strftime('%H:%M:%S')}] run={run_state} media={media_state}", flush=True)
            last_run_state, last_media_state = run_state, media_state
        if run_state == "succeeded":
            jobs = [{"id": m["id"], "state": m.get("state"), "stage": m.get("stage"),
                     "video": m.get("video"), "duration": m.get("duration_seconds")} for m in detail.get("media", [])]
            print("FINAL:", json.dumps(jobs, ensure_ascii=False), flush=True)
            return
        if run_state in {"blocked", "failed"}:
            print("RUN STOPPED:", json.dumps(detail.get("runs")[-1], ensure_ascii=False)[:1500], flush=True)
            sys.exit(2)
        time.sleep(POLL_SECONDS)
    print("TIMEOUT waiting for run", flush=True)
    sys.exit(3)


if __name__ == "__main__":
    main()
