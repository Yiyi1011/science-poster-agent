"""Immutable source snapshots, versions and durable operation state. Local single-user MVP."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.studio_models import ProjectInput


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    root = Path(os.getenv("SCIENCE_POSTER_DATA_DIR") or Path(__file__).resolve().parents[3] / "artifacts")
    root.mkdir(parents=True, exist_ok=True)
    # WPS cloud sync can hold transient file locks on this folder; WAL plus a
    # longer busy timeout keeps brief sync bursts from aborting media jobs.
    db = sqlite3.connect(root / "studio.sqlite3", timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, input TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS research(project TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY, project TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS versions(project TEXT, number INTEGER, payload TEXT NOT NULL,
            PRIMARY KEY(project, number));
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project TEXT, request TEXT, state TEXT,
            stage TEXT, error TEXT DEFAULT '', updated TEXT);
    """)
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def create_project(data: ProjectInput):
    project_id = str(uuid4())
    with connection() as db:
        db.execute("INSERT INTO projects VALUES(?,?,?)", (project_id, data.model_dump_json(), now()))
    return get_project(project_id)


def list_projects():
    with connection() as db:
        rows = db.execute("SELECT id,input,created FROM projects ORDER BY created DESC LIMIT 100").fetchall()
    return [{"id": r["id"], "topic": json.loads(r["input"])["topic"], "created_at": r["created"]} for r in rows]


def get_project(project_id):
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError("项目不存在")
        versions = db.execute("SELECT payload FROM versions WHERE project=? ORDER BY number", (project_id,)).fetchall()
        runs = db.execute("SELECT id,state,stage,error,updated FROM runs WHERE project=? ORDER BY updated", (project_id,)).fetchall()
        research = db.execute("SELECT payload FROM research WHERE project=?", (project_id,)).fetchone()
        media = db.execute("SELECT payload FROM media WHERE project=? ORDER BY rowid", (project_id,)).fetchall()
    return {"id": row["id"], "input": json.loads(row["input"]), "created_at": row["created"],
            "versions": [json.loads(v["payload"]) for v in versions], "runs": [dict(r) for r in runs],
            "research": json.loads(research["payload"]) if research else None,
            "media": [json.loads(m["payload"]) for m in media]}


def save_research(project_id, payload):
    # Separate immutable provenance snapshot; original user input is never overwritten.
    with connection() as db:
        db.execute("INSERT INTO research VALUES(?,?)", (project_id, json.dumps(payload, ensure_ascii=False)))


def reserve(project_id, request):
    """Exactly one in-flight call per project; retries don't silently rebill."""
    request_id = str(request.request_id)
    serialized = request.model_dump_json()
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
            raise KeyError("项目不存在")
        existing = db.execute("SELECT * FROM runs WHERE id=?", (request_id,)).fetchone()
        if existing:
            if existing["project"] != project_id or existing["request"] != serialized:
                raise ValueError("同一个请求编号不可用于不同操作")
            return False
        if db.execute("SELECT 1 FROM runs WHERE project=? AND state='running'", (project_id,)).fetchone():
            raise ValueError("本项目正在处理，请等待完成后再操作")
        if any(json.loads(r[0])["state"] == "running" for r in db.execute("SELECT payload FROM media WHERE project=?", (project_id,))):
            raise ValueError("正在生成媒体，请等待完成再修订脚本")
        version = db.execute("SELECT COALESCE(MAX(number),0) FROM versions WHERE project=?", (project_id,)).fetchone()[0]
        if version != request.expected_version:
            raise ValueError("项目已有新版本，请刷新后重试")
        db.execute("INSERT INTO runs(id,project,request,state,stage,updated) VALUES(?,?,?,'running','准备资料',?)",
                   (request_id, project_id, serialized, now()))
    return True


def stage(request_id, label, state="running", error=""):
    with connection() as db:
        db.execute("UPDATE runs SET stage=?,state=?,error=?,updated=? WHERE id=?",
                   (label, state, error, now(), str(request_id)))


def append_version(project_id, payload):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        number = db.execute("SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE project=?", (project_id,)).fetchone()[0]
        result = dict(payload, version=number, created_at=now())
        db.execute("INSERT INTO versions VALUES(?,?,?)", (project_id, number, json.dumps(result, ensure_ascii=False)))
    return result


def recover_interrupted_runs():
    # Called once on this single-worker application's startup, never while another worker is active.
    with connection() as db:
        db.execute("UPDATE runs SET state='failed',stage='服务重启后已停止',error='操作被中断；已有版本保留，请检查后重新运行。',updated=? WHERE state='running'", (now(),))
        for row in db.execute("SELECT id,payload FROM media").fetchall():
            payload = json.loads(row["payload"])
            if payload["state"] == "running":
                payload.update(state="failed", stage="服务重启，保留候选文件；不会自动重新收费生成")
                db.execute("UPDATE media SET payload=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), row["id"]))


def reserve_media(project_id, request):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT project,version,payload FROM media WHERE id=?", (str(request.request_id),)).fetchone()
        if existing:
            if existing["project"] != project_id or existing["version"] != request.expected_version or json.loads(existing["payload"]).get("renderer", "illustrated") != request.renderer:
                raise ValueError("媒体请求编号已用于其他版本")
            return False
        row = db.execute("SELECT payload FROM versions WHERE project=? ORDER BY number DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            raise ValueError("请先生成有依据的脚本")
        version = json.loads(row[0])
        if version["version"] != request.expected_version:
            raise ValueError("脚本已有新版本，请刷新")
        if version.get("mode") != "bailian" or version.get("review_status") not in {"ai_checked_human_pending", "needs_human_review"}:
            raise ValueError("脚本还未通过基础检查，不能生成收费媒体")
        if db.execute("SELECT 1 FROM runs WHERE project=? AND state='running'", (project_id,)).fetchone():
            raise ValueError("请等待脚本审核完成")
        for r in db.execute("SELECT version,payload FROM media WHERE project=?", (project_id,)):
            prior = json.loads(r["payload"])
            needs_changes = any(h.get("status") == "needs_changes" for h in prior.get("human_reviews", []))
            if prior["state"] == "running" or (r["version"] == request.expected_version and prior["state"] == "succeeded" and not needs_changes and prior.get("renderer", "illustrated") == request.renderer):
                raise ValueError("该版已有媒体或正在生成，不重复收费；请查看结果或先修改脚本")
        payload = {"id": str(request.request_id), "version": request.expected_version, "state": "running", "stage": "准备卡通视频" if request.renderer == "cartoon" else "准备生成插画与有声预览",
                   "events": [], "scenes": [], "files": [], "created_at": now(), "renderer": request.renderer,
                   "kind": "千问规划+程序卡通动作+AI旁白字幕；非视频大模型" if request.renderer == "cartoon" else "AI插画+程序镜头运动+AI配音；非视频大模型原生动画"}
        db.execute("INSERT INTO media VALUES(?,?,?,?)", (str(request.request_id), project_id, request.expected_version, json.dumps(payload, ensure_ascii=False)))
    return True


def save_media(project_id, payload):
    with connection() as db:
        db.execute("UPDATE media SET payload=? WHERE project=? AND id=?", (json.dumps(payload, ensure_ascii=False), project_id, payload["id"]))
