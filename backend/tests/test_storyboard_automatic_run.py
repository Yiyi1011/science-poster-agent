"""Automatic-first flow: no manual apply/save and no model charges."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import storyboard_editor as editor

URL = "/api/videos/editor/solar"


@pytest.fixture
def client(tmp_path):
    with patch.object(editor, "store_path", return_value=tmp_path / "editor.sqlite3"), \
         patch("httpx.AsyncClient", side_effect=AssertionError("No cloud calls in local automatic flow")):
        yield TestClient(app)


def request(long=True, version=0):
    scenes = editor.editable_scenes()
    if long:
        scenes[2]["subtitle_cards"][0] = "耀斑发出的辐射约八分钟后到达地球，可能影响向阳一侧的部分短波通信。"
    return {"scenes": scenes, "run_id": str(uuid4()), "expected_version": version}


def test_single_action_automatically_saves_and_logs(client):
    payload = request()
    response = client.post(URL+"/auto-run", json=payload)
    assert response.status_code == 200
    result = response.json()
    saved, run = result["snapshot"], result["run"]
    assert saved["version"] == 1
    assert len(run["changes"]) == 2
    assert len(run["steps"]) == 4
    assert len(saved["auto_correction"]["steps"]) == 4
    assert run["before_error_count"] == 1 and run["after_error_count"] == 0
    assert run["cloud_calls"] == 0 and not run["media_updated"]
    assert run["verified_by_server"] and run["new_version_created"]
    assert "".join(saved["scenes"][2]["subtitle_cards"]) == "".join(payload["scenes"][2]["subtitle_cards"])
    assert saved["scenes"][2]["duration_seconds"] == 10
    assert saved["analysis"]["requires_science_review"]
    assert saved["analysis"]["tts_scene_count"] == 0
    assert run["outcome"] == "needs_review"
    latest = client.get(URL).json()
    assert latest["automation_runs"][0] == run
    assert latest["scenes"] == saved["scenes"]
    assert "input_scenes" not in run
    with sqlite3.connect(editor.store_path()) as db:
        audit = json.loads(db.execute("SELECT payload FROM automatic_runs").fetchone()[0])
    assert audit["input_scenes"] == payload["scenes"]


def test_noop_check_retains_audit_without_fake_version(client):
    response = client.post(URL+"/auto-run", json=request(long=False)).json()
    assert response["snapshot"]["version"] == 0
    assert response["run"]["changes"] == []
    assert response["run"]["outcome"] == "no_change"
    assert response["run"]["steps"][1]["status"] == "no_change"
    assert not response["run"]["new_version_created"]
    assert len(client.get(URL).json()["automation_runs"]) == 1


def test_identical_network_retry_is_idempotent(client):
    payload = request()
    first = client.post(URL+"/auto-run", json=payload).json()
    second = client.post(URL+"/auto-run", json=payload).json()
    assert second["replayed"] and second["run"] == first["run"]
    assert second["snapshot"]["version"] == 1
    assert len(second["snapshot"]["automation_runs"]) == 1


def test_same_run_id_with_changed_input_rejected(client):
    payload = request()
    client.post(URL+"/auto-run", json=payload)
    payload["scenes"][0]["title"] = "改过标题"
    assert client.post(URL+"/auto-run", json=payload).status_code == 409
    assert len(client.get(URL).json()["automation_runs"]) == 1


def test_stale_version_does_not_run_or_erase_content(client):
    first = client.post(URL+"/auto-run", json=request()).json()
    assert client.post(URL+"/auto-run", json=request()).status_code == 409
    latest = client.get(URL).json()
    assert latest["scenes"] == first["snapshot"]["scenes"]
    assert len(latest["automation_runs"]) == 1


def test_parallel_runs_only_one_wins(client):
    payloads = [request(), request()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda p: client.post(URL+"/auto-run", json=p), payloads))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(client.get(URL).json()["automation_runs"]) == 1


def test_cannot_fake_extra_automatic_changes(client):
    payload = request()
    payload["changes"] = [{"field": "narration", "after": "假修改"}]
    assert client.post(URL+"/auto-run", json=payload).status_code == 422


def test_manual_edits_distinguished_from_system_changes(client):
    payload = request()
    payload["scenes"][0]["narration"] += "这是原文之外的输入。"
    result = client.post(URL+"/auto-run", json=payload).json()
    assert all(c["field"] != "narration" for c in result["run"]["changes"])
    assert any(c["scene_id"] == "SW-A03-1" for c in result["run"]["input_edits_before_automation"])
    assert result["snapshot"]["analysis"]["tts_scene_count"] == 1
    assert result["run"]["outcome"] == "needs_review"


def test_unfixable_problem_not_silently_dropped(client):
    payload = request(False)
    payload["scenes"][0]["subtitle_cards"] = ["长"*120]
    result = client.post(URL+"/auto-run", json=payload).json()
    assert result["snapshot"]["scenes"][0]["subtitle_cards"] == ["长"*120]
    assert result["run"]["skipped"]
    assert result["run"]["after_error_count"] == 1
    assert result["run"]["outcome"] == "needs_review"


def test_later_manual_save_keeps_run_history_without_false_auto_label(client):
    first = client.post(URL+"/auto-run", json=request()).json()["snapshot"]
    first["scenes"][0]["title"] = "人工改标题"
    result = client.put(URL, json={"scenes":first["scenes"],"expected_version":1,"note":"人工改标题"}).json()
    assert result["version"] == 2
    assert result["auto_correction"] is None
    assert result["automation_runs"][0]["result_version"] == 1


def test_audit_failure_rolls_back_draft_and_run(client):
    client.post(URL+"/auto-run", json=request(False))
    with sqlite3.connect(editor.store_path()) as db:
        db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON automatic_runs BEGIN SELECT RAISE(ABORT, 'test write failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        client.post(URL+"/auto-run", json=request())
    latest = client.get(URL).json()
    assert latest["version"] == 0 and len(latest["automation_runs"]) == 1


def test_history_bounded_and_complete_records_preserved(client):
    for _ in range(12):
        assert client.post(URL+"/auto-run", json=request(False)).status_code == 200
    assert len(client.get(URL).json()["automation_runs"]) == 10
    with sqlite3.connect(editor.store_path()) as db:
        assert db.execute("SELECT count(*) FROM automatic_runs").fetchone()[0] == 12
