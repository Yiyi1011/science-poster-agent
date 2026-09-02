import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import APIRouter, HTTPException, Request, Response, Query

from app.config import settings
from app.studio_models import ProjectInput, RunInput, MediaInput
from fastapi.responses import FileResponse
from app.services import studio_store as store
from app.services.studio_pipeline import execute
from app.services.studio_export import export_zip, poster_svg
from app.services.public_access import owner_from

router = APIRouter(prefix="/api/studio", tags=["Cross-topic studio"])
tasks: set[asyncio.Task] = set()
_job_slots: asyncio.Semaphore | None = None
_job_slots_size = 0


def _quota(request: Request, action: str, limit: int, daily: bool = False) -> None:
    if not settings.public_access_enabled:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d" if daily else "%Y-%m-%dT%H")
    try:
        store.consume_public_quota(owner_from(request), action, stamp, limit)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from None


def _quota_spec(request: Request, action: str, limit: int) -> tuple[str, str, str, int] | None:
    if not settings.public_access_enabled:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    return owner_from(request), action, stamp, limit


def _slots() -> asyncio.Semaphore:
    global _job_slots, _job_slots_size
    if _job_slots is None or _job_slots_size != settings.public_max_active_jobs:
        _job_slots = asyncio.Semaphore(settings.public_max_active_jobs)
        _job_slots_size = settings.public_max_active_jobs
    return _job_slots


async def _within_slot(operation):
    async with _slots():
        await operation


def _schedule(operation) -> None:
    if len(tasks) >= settings.public_max_queued_jobs:
        operation.close()
        raise HTTPException(429, "当前生成队列已满，请稍后再试；已有项目不会丢失")
    task = asyncio.create_task(_within_slot(operation))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def execute_with_video(project_id, request):
    await execute(project_id, request)
    project = store.get_project(project_id)
    run = next(r for r in project["runs"] if r["id"] == str(request.request_id))
    if not request.make_video or settings.mock_ai or run["state"] != "succeeded":
        return
    from app.services.studio_media import execute_media
    # A run may finish on the fallback path "最后一轮修订未通过，沿用本轮已审核
    # 通过的版本继续制作": the newest version is then marked blocked, while an
    # earlier version already passed review. Media must target the newest
    # eligible version, otherwise the accepted draft never gets its video.
    target = next((v for v in reversed(project["versions"])
                   if v.get("review_status") in {"ai_checked_human_pending", "needs_human_review"}), None)
    if target is None:
        return
    media_request = MediaInput(request_id=uuid5(NAMESPACE_URL, str(request.request_id) + "/cartoon"),
                               expected_version=target["version"], renderer="cartoon")
    try:
        fresh = store.reserve_media(project_id, media_request)
    except ValueError:
        return  # A competing operation already owns the version; never duplicate paid work.
    if fresh:
        await execute_media(project_id, media_request)


@router.get("/presets")
def presets():
    return json.loads((Path(__file__).parent / "data" / "studio-presets.json").read_text(encoding="utf-8"))


def lookup(project_id, owner: str | None = None):
    try:
        return store.get_project(str(project_id), owner=owner)
    except KeyError:
        raise HTTPException(404, "项目不存在") from None


@router.get("/projects")
def projects(request: Request):
    return store.list_projects(owner_from(request))


@router.post("/projects", status_code=201)
def create(payload: ProjectInput, request: Request):
    _quota(request, "project", settings.public_projects_per_day, daily=True)
    return store.create_project(payload, owner_from(request))


@router.get("/projects/{project_id}")
def detail(project_id: UUID, request: Request):
    return lookup(project_id, owner_from(request))


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID, request: Request):
    """软删除：项目从列表消失但数据完整保留，可恢复。"""
    try:
        store.archive_project(str(project_id), "用户删除", owner_from(request))
    except KeyError:
        raise HTTPException(404, "项目不存在") from None
    return {"ok": True}


@router.post("/projects/{project_id}/run", status_code=202)
async def run(project_id: UUID, payload: RunInput, request: Request):
    lookup(project_id, owner_from(request))
    if not store.has_run_request(payload.request_id) and len(tasks) >= settings.public_max_queued_jobs:
        raise HTTPException(429, "当前生成队列已满，请稍后再试；已有项目不会丢失")
    try:
        fresh = store.reserve(str(project_id), payload,
                              _quota_spec(request, "run", settings.public_runs_per_hour))
    except KeyError:
        raise HTTPException(404, "项目不存在") from None
    except store.PublicQuotaExceeded as exc:
        raise HTTPException(429, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if fresh:
        _schedule(execute_with_video(str(project_id), payload))
    return lookup(project_id, owner_from(request))


@router.get("/projects/{project_id}/poster.svg")
def poster(project_id: UUID, request: Request, revision: int | None = Query(default=None, ge=1)):
    project = lookup(project_id, owner_from(request))
    if not project["versions"]:
        raise HTTPException(409, "项目还没有可预览版本")
    selected = next((v for v in project["versions"] if v["version"] == revision), None) if revision else None
    if revision and selected is None:
        raise HTTPException(404, "版本不存在")
    return Response(poster_svg(project, selected), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/projects/{project_id}/export")
def download(project_id: UUID, request: Request):
    project = lookup(project_id, owner_from(request))
    if not project["versions"]:
        raise HTTPException(409, "项目还没有可导出版本")
    if any(r["state"] == "running" for r in project["runs"]):
        raise HTTPException(409, "请等待本轮审核完成再导出")
    return Response(export_zip(project), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="scivis-{project_id}-v{project["versions"][-1]["version"]}.zip"',
        "Cache-Control": "no-store"})


@router.post("/projects/{project_id}/media", status_code=202)
async def media(project_id: UUID, payload: MediaInput, request: Request):
    from app.services.studio_media import execute_media
    lookup(project_id, owner_from(request))
    if not store.has_media_request(payload.request_id) and len(tasks) >= settings.public_max_queued_jobs:
        raise HTTPException(429, "当前生成队列已满，请稍后再试；已有项目不会丢失")
    try:
        fresh = store.reserve_media(str(project_id), payload,
                                    _quota_spec(request, "media", settings.public_media_per_hour))
    except store.PublicQuotaExceeded as exc:
        raise HTTPException(429, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if fresh:
        _schedule(execute_media(str(project_id), payload))
    return lookup(project_id, owner_from(request))


@router.get("/projects/{project_id}/media/{job_id}/{filename}")
def media_file(project_id: UUID, job_id: UUID, filename: str, request: Request):
    from app.services.studio_media import directory
    project = lookup(project_id, owner_from(request))
    job = next((m for m in project["media"] if m["id"] == str(job_id)), None)
    if not job or filename not in job["files"] or Path(filename).name != filename or "\\" in filename:
        raise HTTPException(404, "媒体文件不存在")
    path = directory(str(project_id), str(job_id)) / filename
    if not path.is_file():
        raise HTTPException(404, "媒体文件尚未生成")
    return FileResponse(path, headers={"Cache-Control": "no-store"})
