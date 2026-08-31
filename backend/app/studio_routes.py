import asyncio
import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, Query

from app.config import settings
from app.studio_models import ProjectInput, RunInput
from app.services import studio_store as store
from app.services.studio_pipeline import execute
from app.services.studio_export import export_zip, poster_svg

router = APIRouter(prefix="/api/studio", tags=["Cross-topic studio"])
tasks: set[asyncio.Task] = set()


@router.get("/presets")
def presets():
    return json.loads((Path(__file__).parent / "data" / "studio-presets.json").read_text(encoding="utf-8"))


def lookup(project_id):
    try:
        return store.get_project(str(project_id))
    except KeyError:
        raise HTTPException(404, "项目不存在") from None


@router.get("/projects")
def projects():
    return store.list_projects()


@router.post("/projects", status_code=201)
def create(request: ProjectInput):
    return store.create_project(request)


@router.get("/projects/{project_id}")
def detail(project_id: UUID):
    return lookup(project_id)


@router.post("/projects/{project_id}/run", status_code=202)
async def run(project_id: UUID, request: RunInput):
    try:
        fresh = store.reserve(str(project_id), request)
    except KeyError:
        raise HTTPException(404, "项目不存在") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if fresh:
        task = asyncio.create_task(execute(str(project_id), request))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    return lookup(project_id)


@router.get("/projects/{project_id}/poster.svg")
def poster(project_id: UUID, revision: int | None = Query(default=None, ge=1)):
    project = lookup(project_id)
    if not project["versions"]:
        raise HTTPException(409, "项目还没有可预览版本")
    selected = next((v for v in project["versions"] if v["version"] == revision), None) if revision else None
    if revision and selected is None:
        raise HTTPException(404, "版本不存在")
    return Response(poster_svg(project, selected), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/projects/{project_id}/export")
def download(project_id: UUID):
    project = lookup(project_id)
    if not project["versions"]:
        raise HTTPException(409, "项目还没有可导出版本")
    if any(r["state"] == "running" for r in project["runs"]):
        raise HTTPException(409, "请等待本轮审核完成再导出")
    return Response(export_zip(project), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="scivis-{project_id}-v{project["versions"][-1]["version"]}.zip"',
        "Cache-Control": "no-store"})
