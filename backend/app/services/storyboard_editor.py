"""Local-only editable draft store. No model clients and no media overwrite.

Compare with the immutable rendered baseline, not just the last draft: a later
subtitle edit must not erase an earlier pending narration regeneration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.config import settings

BASELINE_PATH = Path(__file__).resolve().parents[1] / "data" / "solar-editor-baseline.json"
EDITABLE = ("scene_id", "title", "duration_seconds", "narration", "subtitle_cards", "visual_direction")
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
Caption = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class EditedScene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: Annotated[str, StringConstraints(pattern=r"^SW-A03-[1-7]$")]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    duration_seconds: float = Field(ge=3, le=30, allow_inf_nan=False)
    narration: Text
    subtitle_cards: list[Caption] = Field(min_length=1, max_length=6)
    visual_direction: Text


class AnalyzeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenes: list[EditedScene] = Field(min_length=7, max_length=7)


class SaveDraft(AnalyzeDraft):
    expected_version: int = Field(ge=0)
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)]
    auto_fix_base: list[EditedScene] | None = Field(default=None, min_length=7, max_length=7)


class AutomaticRun(AnalyzeDraft):
    expected_version: int = Field(ge=0)
    run_id: UUID


class VersionConflict(Exception):
    pass


def baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def editable_scenes() -> list[dict]:
    return [{key: scene[key] for key in EDITABLE} for scene in baseline()["scenes"]]


def validate_scene_identity(scenes: list[EditedScene]) -> None:
    if [s.scene_id for s in scenes] != [s["scene_id"] for s in baseline()["scenes"]]:
        raise ValueError("此阶段保留7个镜头的身份与顺序，不能重复、删除或重排。")


def analyze(scenes: list[EditedScene]) -> dict:
    validate_scene_identity(scenes)
    reports = []
    frame_cursor = 0
    tts_characters = 0
    for scene, original in zip(scenes, baseline()["scenes"]):
        data = scene.model_dump()
        changed = [key for key in EDITABLE if data[key] != original[key]]
        tts = "narration" in changed
        frames = math.ceil(scene.duration_seconds * 24 - 1e-8)
        duration = frames / 24
        issues = []
        if any(len(c) > 18 for c in scene.subtitle_cards):
            issues.append({"code": "caption_too_long", "severity": "error", "message": "字幕超过18字，请拆成更短的要点卡。"})
        if duration / len(scene.subtitle_cards) < 2.5:
            issues.append({"code": "caption_too_fast", "severity": "error", "message": "每条要点字幕不足2.5秒，请延长镜头或减少要点。"})
        if not tts and duration + 1e-6 < original["audio_duration_seconds"] + 0.8:
            issues.append({"code": "audio_would_be_cut", "severity": "error", "message": f"原配音需至少{original['audio_duration_seconds'] + 0.8:.2f}秒（含停顿）；不能截断或强行加速。"})
        if tts:
            tts_characters += len(scene.narration)
            issues.append({"code": "new_audio_duration_unknown", "severity": "warning", "message": "新旁白尚未合成；镜头时长只是预排，需按新录音重新核对。"})
        science_review = any(key != "duration_seconds" for key in changed)
        if science_review:
            issues.append({"code": "meaning_needs_review", "severity": "review", "message": "文字或画面含义已变化，需对照来源与科学边界复核；不能沿用旧版认可。"})
        reports.append({"scene_id": scene.scene_id, "changed_fields": changed,
                        "requires_tts": tts, "requires_render": bool(changed), "requires_science_review": science_review,
                        "audio_action": "regenerate_after_review" if tts else "reuse_existing_audio",
                        "render_action": "pending_local_render" if changed else "reuse_baseline_scene",
                        "start_seconds": frame_cursor / 24, "duration_seconds": duration, "issues": issues})
        frame_cursor += frames
    changes = any(item["changed_fields"] for item in reports)
    blocked = any(issue["severity"] == "error" for item in reports for issue in item["issues"])
    return {"scenes": reports, "duration_seconds": frame_cursor / 24, "frames": frame_cursor,
            "tts_scene_count": sum(s["requires_tts"] for s in reports), "tts_characters": tts_characters,
            "estimated_tts_cost_cny": round(tts_characters / 10000 * settings.qwen_tts_price_per_10k_chars, 6),
            "price_note": "仅按当前配置估算待重配字符费用，非实付；本操作不调用模型。",
            "requires_recomposition": changes, "has_validation_errors": blocked,
            "requires_science_review": any(s["requires_science_review"] for s in reports),
            "status": "blocked" if blocked else "draft_needs_review" if changes else "matches_accepted_media",
            "cloud_calls": 0, "media_updated": False, "can_generate_from_editor": False}


def _split_caption(value: str) -> list[str] | None:
    """Split without adding/deleting even a punctuation mark or whitespace."""
    pieces = []
    remaining = value
    while len(remaining) > 18:
        positions = [i for i in range(1, 19) if not remaining[i-1].isspace() and not remaining[i].isspace()]
        if not positions:
            return None
        punctuation = [i for i in positions if i >= 6 and remaining[i-1] in "，。；：！？、,.;:!?"]
        end = max(punctuation or positions)
        pieces.append(remaining[:end])
        remaining = remaining[end:]
    pieces.append(remaining)
    if any(not part or part != part.strip() for part in pieces):
        return None
    assert "".join(pieces) == value
    return pieces


def auto_fix(scenes: list[EditedScene]) -> dict:
    validate_scene_identity(scenes)
    fixed, changes, skipped = [], [], []
    for scene, original in zip(scenes, baseline()["scenes"]):
        data = scene.model_dump()
        cards = []
        for caption in scene.subtitle_cards:
            pieces = _split_caption(caption)
            if pieces is None:
                cards = []
                break
            cards.extend(pieces)
        if cards and len(cards) <= 6:
            if cards != scene.subtitle_cards:
                assert "".join(cards) == "".join(scene.subtitle_cards)
                data["subtitle_cards"] = cards
                changes.append({"scene_id":scene.scene_id,"field":"subtitle_cards","before":scene.subtitle_cards,"after":cards,
                                "reason":"在标点附近拆分长字幕，每条不超过18字；保留全部原文，不改科学表述。"})
        elif any(len(c)>18 for c in scene.subtitle_cards):
            skipped.append({"scene_id":scene.scene_id,"message":"无法在保留原文且不超过6条字幕的条件下安全拆分，请人工精简。"})
        minimum = len(data["subtitle_cards"]) * 2.5
        if scene.narration == original["narration"]:
            minimum = max(minimum, original["audio_duration_seconds"] + 0.8)
        if data["duration_seconds"] + 1e-6 < minimum:
            adjusted = math.ceil(minimum*24-1e-8) / 24
            changes.append({"scene_id":scene.scene_id,"field":"duration_seconds","before":data["duration_seconds"],"after":adjusted,
                            "reason":"延长本镜头，给每条字幕至少2.5秒，并容纳可复用的原配音；不加速语音。"})
            data["duration_seconds"] = adjusted
        fixed.append(EditedScene.model_validate(data))
    canonical = json.dumps([s.model_dump() for s in scenes],ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return {"method":"local_format_rules","input_sha256":hashlib.sha256(canonical.encode()).hexdigest(),
            "scenes":[s.model_dump() for s in fixed],"changes":changes,"skipped":skipped,"analysis":analyze(fixed),
            "cloud_calls":0,"media_updated":False,"stage":"proposal_not_applied",
            "boundary":"只自动拆分字幕和延长时长；不改写旁白或科学结论，不替代科学审核。"}


def store_path() -> Path:
    root = Path(settings.runtime_data_dir) if settings.runtime_data_dir else Path(__file__).resolve().parents[3] / "artifacts"
    return (root / "storyboard-editor" / "solar-drafts.sqlite3").resolve()


def initial_snapshot() -> dict:
    return {"version": 0, "saved_at": None, "note": "用户认可的有声试听版基线", "scenes": editable_scenes(), "changes_from_previous": [], "auto_correction":None}


def read_snapshot(version: int | None = None, path: Path | None = None) -> dict:
    if version == 0:
        return initial_snapshot()
    database = path or store_path()
    if not database.exists():
        if version is not None:
            raise LookupError("版本不存在。")
        return initial_snapshot()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT payload FROM versions ORDER BY version DESC LIMIT 1" if version is None else
                                 "SELECT payload FROM versions WHERE version=?", () if version is None else (version,)).fetchone()
    if row:
        return json.loads(row[0])
    if version is not None:
        raise LookupError("版本不存在。")
    return initial_snapshot()


def history(path: Path | None = None) -> list[dict]:
    database = path or store_path()
    result = []
    if database.exists():
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            rows = connection.execute("SELECT payload FROM versions ORDER BY version DESC LIMIT 50").fetchall()
        for row in rows:
            saved = json.loads(row[0])
            result.append({key: saved[key] for key in ("version", "saved_at", "note")})
    result.append({"version": 0, "saved_at": None, "note": "已认可的有声试听版基线"})
    return result


def response_for(snapshot: dict, path: Path | None = None) -> dict:
    data = baseline()
    runs = automatic_history(path)
    return {**snapshot, "project_id": data["project_id"], "title": data["title"],
            "media_url": data["media_url"], "media_version": "narrated-v001", "acceptance": data["acceptance"],
            "baseline_scenes": data["scenes"], "history": history(path), "automation_runs": runs,
            "analysis": analyze([EditedScene.model_validate(s) for s in snapshot["scenes"]])}


def save(request: SaveDraft, path: Path | None = None) -> dict:
    validate_scene_identity(request.scenes)
    automatic = None
    if request.auto_fix_base is not None:
        proposal = auto_fix(request.auto_fix_base)
        if proposal["scenes"] != [s.model_dump() for s in request.scenes] or not proposal["changes"]:
            raise ValueError("自动修正记录与当前草稿不一致；请重新检查，不能把手动修改伪装为自动修正。")
        automatic = {key: proposal[key] for key in ("method","input_sha256","changes","skipped","boundary")}
        automatic.update(stage="applied_to_saved_draft", verified_by_server=True, media_updated=False, cloud_calls=0)
    database = path or store_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    # The transaction serializes concurrent saves; unique version rows are never overwritten.
    with closing(sqlite3.connect(database, timeout=5)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS versions (version INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT payload FROM versions ORDER BY version DESC LIMIT 1").fetchone()
        current = json.loads(row[0]) if row else initial_snapshot()
        if current["version"] != request.expected_version:
            raise VersionConflict("已有新版本，请先导出当前草稿，再加载最新版本合并。不会覆盖其他窗口的修改。")
        proposed = [scene.model_dump() for scene in request.scenes]
        if proposed == current["scenes"]:
            raise ValueError("内容没有变化，无需创建重复版本。")
        diff = [{"scene_id": scene["scene_id"], "fields": {
                    key: {"before": old[key], "after": scene[key]} for key in EDITABLE if old[key] != scene[key]}}
                for old, scene in zip(current["scenes"], proposed) if scene != old]
        snapshot = {"version": current["version"]+1, "saved_at": datetime.now(timezone.utc).isoformat(),
                    "note": request.note, "scenes": proposed, "changes_from_previous": diff, "auto_correction":automatic}
        connection.execute("INSERT INTO versions(version,payload) VALUES(?,?)",
                           (snapshot["version"], json.dumps(snapshot, ensure_ascii=False)))
    return response_for(snapshot, database)


def automatic_history(path: Path | None = None) -> list[dict]:
    database = path or store_path()
    if not database.exists():
        return []
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        if not connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automatic_runs'").fetchone():
            return []
        rows = connection.execute("SELECT payload FROM automatic_runs ORDER BY rowid DESC LIMIT 10").fetchall()
    # Detailed field diffs are retained; complete input snapshots stay in the local audit DB.
    return [{k: v for k, v in json.loads(row[0]).items() if k != "input_scenes"} for row in rows]


def run_automatic(request: AutomaticRun, path: Path | None = None) -> dict:
    """One action: inspect -> repair -> recheck -> atomically save draft AND audit.

    The caller supplies input, not proposed corrections. We compute all changes.
    A stable run_id makes a network retry idempotent. No-op checks get an audit
    record but do not manufacture draft versions. Original media is never touched.
    """
    validate_scene_identity(request.scenes)
    database = path or store_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    now = lambda: datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(database, timeout=5)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS versions (version INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS automatic_runs (run_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT payload FROM versions ORDER BY version DESC LIMIT 1").fetchone()
        current = json.loads(row[0]) if row else initial_snapshot()
        previous = connection.execute("SELECT request_hash,payload FROM automatic_runs WHERE run_id=?", (str(request.run_id),)).fetchone()
        replayed = bool(previous)
        if previous:
            if previous[0] != digest:
                raise VersionConflict("此运行编号已用于另一份输入；请加载最新版本后重试。")
            audit = json.loads(previous[1])
        else:
            if current["version"] != request.expected_version:
                raise VersionConflict("已有新版本，本轮自动修正未执行。请先导出当前草稿，再加载最新版本。")
            started = now()
            input_scenes = [scene.model_dump() for scene in request.scenes]
            before_analysis = analyze(request.scenes)
            steps = [{"label": "检查7个镜头", "status": "completed", "at": now()}]
            result = auto_fix(request.scenes)
            steps.append({"label": "自动修正字幕与时长", "status": "completed" if result["changes"] else "no_change", "at": now()})
            after_analysis = result["analysis"]
            pending = after_analysis["has_validation_errors"] or after_analysis["requires_science_review"]
            steps.append({"label": "复检并标出待审核项", "status": "needs_review" if pending else "completed", "at": now()})
            proposed = result["scenes"]
            create_version = proposed != current["scenes"]
            input_edits = [{"scene_id": s["scene_id"], "fields": [k for k in EDITABLE if old[k] != s[k]]}
                           for old, s in zip(current["scenes"], input_scenes) if old != s]
            audit = {key: result[key] for key in ("method", "input_sha256", "changes", "skipped", "boundary")}
            audit.update(run_id=str(request.run_id), started_at=started, completed_at=now(),
                         stage="completed", verified_by_server=True, cloud_calls=0, media_updated=False,
                         base_version=current["version"], result_version=current["version"] + int(create_version),
                         new_version_created=create_version, input_scenes=input_scenes,
                         input_edits_before_automation=input_edits, steps=steps,
                         outcome="needs_review" if pending else "corrected" if result["changes"] else "no_change",
                         before_error_count=sum(i["severity"] == "error" for s in before_analysis["scenes"] for i in s["issues"]),
                         after_error_count=sum(i["severity"] == "error" for s in after_analysis["scenes"] for i in s["issues"]))
            steps.append({"label": "保存修订与运行记录" if create_version else "保存检查记录（无需新版本）", "status": "completed", "at": now()})
            if create_version:
                automatic = {k: v for k, v in audit.items() if k != "input_scenes"}
                automatic["stage"] = "applied_to_saved_draft"
                current = {"version": audit["result_version"], "saved_at": now(),
                           "note": f"自动检查并保存：{len(result['changes'])}项系统修正" + ("；含运行前输入改动" if input_edits else ""),
                           "scenes": proposed, "auto_correction": automatic,
                           "changes_from_previous": [{"scene_id": s["scene_id"], "fields": {
                               k: {"before": old[k], "after": s[k]} for k in EDITABLE if old[k] != s[k]}}
                               for old, s in zip(current["scenes"], proposed) if old != s]}
                connection.execute("INSERT INTO versions(version,payload) VALUES(?,?)", (current["version"], json.dumps(current, ensure_ascii=False)))
            audit["completed_at"] = now()
            connection.execute("INSERT INTO automatic_runs(run_id,request_hash,payload) VALUES(?,?,?)",
                               (str(request.run_id), digest, json.dumps(audit, ensure_ascii=False)))
    return {"snapshot": response_for(current, database), "run": {k: v for k, v in audit.items() if k != "input_scenes"}, "replayed": replayed}
