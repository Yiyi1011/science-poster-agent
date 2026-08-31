import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import APIRouter, HTTPException, Response, Query

from app.config import settings
from app.studio_models import ProjectInput, RunInput, MediaInput
from fastapi.responses import FileResponse
from app.services import studio_store as store
from app.services.studio_pipeline import execute
from app.services.studio_export import export_zip, poster_svg

router = APIRouter(prefix="/api/studio", tags=["Cross-topic studio"])
tasks: set[asyncio.Task] = set()


async def execute_with_video(project_id, request):
    await execute(project_id, request)
    project = store.get_project(project_id)
    run = next(r for r in project["runs"] if r["id"] == str(request.request_id))
    if not request.make_video or settings.mock_ai or run["state"] != "succeeded":
        return
    from app.services.studio_media import execute_media
    media_request = MediaInput(request_id=uuid5(NAMESPACE_URL, str(request.request_id) + "/cartoon"),
                               expected_version=project["versions"][-1]["version"], renderer="cartoon")
    try:
        fresh = store.reserve_media(project_id, media_request)
    except ValueError:
        return  # A competing operation already owns the version; never duplicate paid work.
    if fresh:
        await execute_media(project_id, media_request)


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
        task = asyncio.create_task(execute_with_video(str(project_id), request))
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


@router.post("/projects/{project_id}/media", status_code=202)
async def media(project_id: UUID, request: MediaInput):
    from app.services.studio_media import execute_media
    lookup(project_id)
    try:
        fresh = store.reserve_media(str(project_id), request)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if fresh:
        task = asyncio.create_task(execute_media(str(project_id), request))
        tasks.add(task); task.add_done_callback(tasks.discard)
    return lookup(project_id)


@router.get("/projects/{project_id}/media/{job_id}/{filename}")
def media_file(project_id: UUID, job_id: UUID, filename: str):
    from app.services.studio_media import directory
    project = lookup(project_id)
    job = next((m for m in project["media"] if m["id"] == str(job_id)), None)
    if not job or filename not in job["files"] or Path(filename).name != filename or "\\" in filename:
        raise HTTPException(404, "媒体文件不存在")
    path = directory(str(project_id), str(job_id)) / filename
    if not path.is_file():
        raise HTTPException(404, "媒体文件尚未生成")
    return FileResponse(path, headers={"Cache-Control": "no-store"})
