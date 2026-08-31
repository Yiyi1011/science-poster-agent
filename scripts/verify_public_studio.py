"""Explicit, bounded real-Qwen verification. Saves new versions, never rewrites old drafts.

Usage: python scripts/verify_public_studio.py --project UUID [--project UUID]
       python scripts/verify_public_studio.py --question 'science question'
Costs money in real mode. User budget guard remains active. No keys/response headers logged.
"""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.studio_models import RunInput, ProjectInput
from app.services import studio_store as store
from app.services.studio_pipeline import execute, validate_communication
from app.services.studio_export import export_zip
from app.studio_models import StudioDraft


async def main(args):
    if settings.mock_ai:
        raise SystemExit("This verification requires real Bailian mode")
    ids = args.project or []
    if args.question:
        ids.append(store.create_project(ProjectInput(topic=args.question, auto_sources=True))["id"])
    if not ids:
        raise SystemExit("Provide an existing project or a question")
    directory = ROOT / args.output_directory
    directory.mkdir(parents=True, exist_ok=True)
    report = []
    for project_id in ids:
        project = store.get_project(project_id)
        previous = project["versions"][-1]["version"] if project["versions"] else 0
        feedback = ""  # Never inject a previous case's developer feedback into a different topic.
        if args.feedback_file:
            feedback = Path(args.feedback_file).read_text(encoding="utf-8").strip()
        request = RunInput(request_id=uuid4(), expected_version=previous, feedback=feedback, rebuild=args.rebuild, make_video=args.video)
        store.reserve(project_id, request)
        print(json.dumps({"phase": "start", "project": project_id, "previous_version": previous}), flush=True)
        if args.video:
            from app.studio_routes import execute_with_video
            await execute_with_video(project_id, request)
        else:
            await execute(project_id, request)
        result = store.get_project(project_id)
        (directory / f"{project_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        entry = {"project": project_id, "state": result["runs"][-1]["state"], "error": result["runs"][-1]["error"],
                 "sources": len((result.get("research") or {}).get("sources", [])) or len(result["input"]["sources"])}
        if result.get("media"):
            media = result["media"][-1]
            entry["media"] = {k: media.get(k) for k in ("id", "state", "renderer", "stage", "duration_seconds")}
        if result["versions"]:
            version = result["versions"][-1]
            draft = StudioDraft.model_validate(version["draft"])
            entry.update(version=version["version"], scenes=len(draft.scenes), public_poster=draft.public_poster is not None,
                         findings=version["findings"], quality_gates=validate_communication(draft), changes=len(version["changes"]))
            (directory / f"{project_id}-v{version['version']}.zip").write_bytes(export_zip(result))
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (directory / f"report-{datetime.now():%Y%m%d-%H%M%S}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", action="append")
    parser.add_argument("--question")
    parser.add_argument("--output-directory", default="evidence/studio-v040")
    parser.add_argument("--rebuild", action="store_true", help="Rewrite from source input, preserving old versions")
    parser.add_argument("--video", action="store_true", help="Explicitly run the paid automatic cartoon pipeline after text review")
    parser.add_argument("--feedback-file", help="Explicit developer/user feedback text; provenance must be stated in the file")
    asyncio.run(main(parser.parse_args()))
