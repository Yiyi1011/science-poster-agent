"""Explicit bounded paid smoke test (two Qwen topics, no image/TTS purchases).

Run from backend using configured local .env; preserves source and version history.
Never prints provider credentials or raw exception response bodies.
"""
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.studio_models import ProjectInput, RunInput
from app.services import studio_store as store
from app.services.studio_pipeline import execute, validate_evidence
from app.services.studio_export import export_zip
from app.studio_models import StudioDraft


async def main():
    if settings.mock_ai:
        raise SystemExit("Real verification requires MOCK_AI=false; no fabricated success.")
    settings.validate_for_real_ai()
    presets = json.loads((ROOT / "backend/app/data/studio-presets.json").read_text(encoding="utf-8"))
    out = ROOT / "evidence/studio-v020"
    out.mkdir(parents=True, exist_ok=True)
    report = []
    for preset in presets:
        project = store.create_project(ProjectInput.model_validate(preset))
        operation = RunInput(request_id=uuid4(), expected_version=0)
        store.reserve(project["id"], operation)
        print(json.dumps({"phase": "start", "project": project["id"], "topic": preset["topic"]}, ensure_ascii=False), flush=True)
        await execute(project["id"], operation)
        result = store.get_project(project["id"])
        latest = result["versions"][-1] if result["versions"] else None
        entry = {"project": result["id"], "topic": preset["topic"], "state": result["runs"][-1]["state"],
                 "versions": len(result["versions"]), "model": settings.qwen_text_model,
                 "changes": len(latest["changes"]) if latest else 0,
                 "review_status": latest["review_status"] if latest else "none",
                 "structural_findings": validate_evidence(StudioDraft.model_validate(latest["draft"]), ProjectInput.model_validate(preset)) if latest else [],
                 "findings": latest["findings"] if latest else [], "error": result["runs"][-1]["error"]}
        report.append(entry)
        (out / f"{result['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if latest:
            (out / f"{result['id']}.zip").write_bytes(export_zip(result))
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
