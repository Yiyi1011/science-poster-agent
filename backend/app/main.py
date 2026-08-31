from __future__ import annotations

import logging
from contextlib import asynccontextmanager
import asyncio
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import (
    KnowledgeAnswer,
    KnowledgeQueryRequest,
    PosterPlan,
    PosterRequest,
    PublicConfig,
    RevisionPlan,
    RevisionRequest,
    VideoStoryboard,
    VisualAssetBundle,
)
from app.services.bailian_app_client import BailianKnowledgeAppClient
from app.services.pipeline import create_poster_plan
from app.services.svg_renderer import render_poster_svg
from app.storyboard_routes import router as storyboard_editor_router
from app.services.visual_workflow import (
    build_revision_plan,
    build_video_storyboard,
    build_visual_asset_bundle,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    from app.services.studio_store import recover_interrupted_runs
    from app.studio_routes import tasks
    recover_interrupted_runs()
    yield
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*list(tasks), return_exceptions=True)

app = FastAPI(
    title="Science Poster Agent API",
    version="0.4.0-preview",
    lifespan=lifespan,
    description="Evidence-driven science poster planning API for the competition MVP.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "mock_ai": settings.mock_ai, "region": settings.region, "service": "science-poster-agent", "version": "0.4.0-preview",
            "instance": sha256(str(Path(__file__).resolve().parents[2]).lower().encode()).hexdigest()[:16]}


@app.get("/api/config/public", response_model=PublicConfig)
async def public_config() -> PublicConfig:
    return PublicConfig(
        app_env=settings.app_env,
        mock_ai=settings.mock_ai,
        region=settings.region,
        text_model=settings.qwen_text_model,
        studio_model=settings.qwen_studio_model,
        knowledge_app_enabled=bool(settings.app_id),
        retrieval_min_score=settings.retrieval_min_score,
    )


@app.post("/api/knowledge/query", response_model=KnowledgeAnswer)
async def query_knowledge(request: KnowledgeQueryRequest) -> KnowledgeAnswer:
    try:
        return await BailianKnowledgeAppClient(settings).query(
            request.question,
            request.session_id,
        )
    except Exception as exc:
        logger.exception("Knowledge query failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail=f"Knowledge query failed: {type(exc).__name__}",
        ) from exc


@app.post("/api/posters/plan", response_model=PosterPlan)
async def plan_poster(request: PosterRequest) -> PosterPlan:
    try:
        return await create_poster_plan(request)
    except Exception as exc:
        # Error details remain server-side in production; no credential-bearing request is returned.
        logger.exception("Poster planning failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"Poster planning failed: {type(exc).__name__}") from exc


@app.post("/api/posters/render-svg")
async def render_svg(plan: PosterPlan) -> Response:
    return Response(
        content=render_poster_svg(plan),
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'inline; filename="science-poster.svg"'},
    )


@app.post("/api/visual-assets/specs", response_model=VisualAssetBundle)
async def plan_visual_assets(plan: PosterPlan) -> VisualAssetBundle:
    return build_visual_asset_bundle(plan)


@app.post("/api/revisions/plan", response_model=RevisionPlan)
async def plan_revision(request: RevisionRequest) -> RevisionPlan:
    return build_revision_plan(request)


@app.post("/api/videos/storyboard", response_model=VideoStoryboard)
async def plan_video_storyboard(plan: PosterPlan) -> VideoStoryboard:
    return build_video_storyboard(plan)


app.include_router(storyboard_editor_router)
from app.studio_routes import router as studio_router
app.include_router(studio_router)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_relative_to(FRONTEND_DIST.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
