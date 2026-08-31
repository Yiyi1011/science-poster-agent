"""Re-encode an existing cartoon with current renderer. No model calls; retain old files."""
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
from app.services.studio_video import compose
from app.studio_models import StudioDraft


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project"); parser.add_argument("job"); parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    p = store.get_project(args.project)
    if any(r["state"] == "running" for r in p["runs"]) or any(m["state"] == "running" for m in p["media"]):
        raise SystemExit("Wait for active project operations")
    job = next(m for m in p["media"] if m["id"] == args.job)
    if job.get("renderer") != "cartoon" or job["state"] != "succeeded":
        raise SystemExit("Only completed cartoons can be re-encoded")
    root = directory(args.project,args.job)
    draft = StudioDraft.model_validate(next(v for v in p["versions"] if v["version"] == job["version"])["draft"])
    images,voices,plans = [],[],[]
    for scene in job["scenes"]:
        candidate = next(c for c in scene["candidates"] if c["file"] == scene["accepted"])
        for name in (scene["accepted"],scene["voice"]["file"]):
            if Path(name).name != name or name not in job["files"]:
                raise SystemExit("Asset is not in the job manifest")
        images.append(root/scene["accepted"]); voices.append(root/scene["voice"]["file"]); plans.append(candidate["plan"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = root/f"render-{stamp}"; folder.mkdir(exist_ok=False)
    result = compose(draft,images,voices,folder,cartoon_plans=plans)
    old_video = job["video"]
    for field in ("video","subtitles"):
        source=folder/result[field]; target=root/f"{source.stem}-{stamp}{source.suffix}"
        if target.exists(): raise SystemExit("Never overwrite old render")
        shutil.copy2(source,target); result[field]=target.name; job["files"].append(target.name)
    job.update(result)
    job.setdefault("render_revisions",[]).append({"at":store.now(),"kind":"program_layout_correction","reason":args.reason,
        "previous_video":old_video,"video":job["video"],"paid_calls":0})
    name=f"manifest-{stamp}.json"; job["files"].append(name)
    (root/name).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding="utf-8")
    store.save_media(args.project,job)
    print(json.dumps({"project":args.project,"job":args.job,"video":job["video"],"duration":job["duration_seconds"],"paid_calls":0},ensure_ascii=False))


if __name__ == "__main__": main()
