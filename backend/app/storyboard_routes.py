"""Read/edit/review planning endpoints; deliberately no generation endpoint."""
from fastapi import APIRouter, HTTPException
from app.services import storyboard_editor as editor

router = APIRouter(prefix="/api/videos/editor/solar", tags=["local-storyboard-editor"])


@router.get("")
def latest() -> dict:
    return editor.response_for(editor.read_snapshot())


@router.get("/versions/{version}")
def version(version: int) -> dict:
    try:
        return editor.response_for(editor.read_snapshot(version))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/analyze")
def analyze(request: editor.AnalyzeDraft) -> dict:
    try:
        return editor.analyze(request.scenes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.put("")
def save(request: editor.SaveDraft) -> dict:
    try:
        return editor.save(request)
    except editor.VersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/auto-fix")
def auto_fix(request: editor.AnalyzeDraft) -> dict:
    try:
        return editor.auto_fix(request.scenes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/auto-run")
def auto_run(request: editor.AutomaticRun) -> dict:
    try:
        return editor.run_automatic(request)
    except editor.VersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
