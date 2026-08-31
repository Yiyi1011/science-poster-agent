from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services import storyboard_editor as editor

URL = "/api/videos/editor/solar"


@pytest.fixture
def client(tmp_path):
    with patch.object(editor, "store_path", return_value=tmp_path / "editor.sqlite3"), \
         patch("httpx.AsyncClient", side_effect=AssertionError("Editor must never call a model")):
        yield TestClient(app)


def request(scenes=None, version=0, note="单元测试修改"):
    return {"scenes": scenes or editor.editable_scenes(), "expected_version": version, "note": note}


def test_read_only_baseline_does_not_create_store(client):
    data = client.get(URL).json()
    assert data["version"] == 0
    assert len(data["scenes"]) == 7
    assert data["analysis"]["tts_scene_count"] == 0
    assert data["analysis"]["status"] == "matches_accepted_media"
    assert data["analysis"]["frames"] == 1618
    assert not editor.store_path().exists()


def test_packaged_baseline_matches_confirmed_narration_and_movie():
    root = Path(__file__).resolve().parents[2]
    timeline = json.loads((Path(__file__).parent / "fixtures/solar-confirmed-timeline.json").read_text(encoding="utf-8"))
    baseline = editor.baseline()
    for packaged, source in zip(baseline["scenes"], timeline["scenes"]):
        assert packaged["scene_id"] == source["id"]
        assert packaged["narration"] == source["narration_draft"]
        assert packaged["subtitle_cards"] == source["subtitle_cards"]
        assert packaged["source_ids"] == source["source_ids"]
        assert abs(packaged["duration_seconds"] - source["duration_seconds"]) < 1e-6
        assert abs(packaged["media_start_seconds"] - source["start_seconds"]) < 1e-6
    movie = root / "frontend/public/solar-animation/media/solar-messengers-narrated-v001.mp4"
    assert hashlib.sha256(movie.read_bytes()).hexdigest() == baseline["media_sha256"]


def test_caption_only_edit_does_not_resynthesize_audio(client):
    scenes = editor.editable_scenes()
    scenes[2]["subtitle_cards"][0] = "从太阳出发，约8分钟到地球"
    result = client.post(URL+"/analyze", json={"scenes":scenes})
    assert result.status_code == 200
    data = result.json()
    assert data["tts_scene_count"] == 0
    assert data["estimated_tts_cost_cny"] == 0
    assert data["scenes"][2]["requires_render"]
    assert data["scenes"][2]["requires_science_review"]
    assert data["cloud_calls"] == 0
    assert not data["media_updated"]
    assert not editor.store_path().exists()


def test_narration_edit_selects_only_one_scene(client):
    scenes = editor.editable_scenes()
    scenes[1]["narration"] += "先分清它们。"
    data = client.post(URL+"/analyze", json={"scenes":scenes}).json()
    assert data["tts_scene_count"] == 1
    assert data["tts_characters"] == len(scenes[1]["narration"])
    assert data["scenes"][1]["requires_tts"]
    assert data["requires_science_review"]
    assert not data["can_generate_from_editor"]


def test_later_edit_retains_earlier_pending_audio(client):
    scenes = editor.editable_scenes()
    scenes[0]["narration"] += "这是一个比喻。"
    first = client.put(URL, json=request(scenes)).json()
    scenes[3]["subtitle_cards"][0] = "粒子抵达所需时间因事件而异"
    second = client.put(URL, json=request(scenes, version=1)).json()
    assert first["version"] == 1 and second["version"] == 2
    assert second["analysis"]["tts_scene_count"] == 1
    assert second["analysis"]["scenes"][0]["requires_tts"]
    assert len(second["changes_from_previous"]) == 1
    assert second["changes_from_previous"][0]["scene_id"] == "SW-A03-4"
    assert client.get(URL+"/versions/1").json()["scenes"] == first["scenes"]


def test_restore_creates_new_version_without_overwrite(client):
    scenes = editor.editable_scenes()
    scenes[0]["title"] = "先问一个问题"
    first = client.put(URL,json=request(scenes)).json()
    restored = client.put(URL,json=request(editor.editable_scenes(),version=1,note="恢复已认可基线")).json()
    assert restored["version"] == 2
    assert restored["analysis"]["status"] == "matches_accepted_media"
    assert client.get(URL+"/versions/1").json()["scenes"] == first["scenes"]


def test_stale_tab_is_conflict_not_overwrite(client):
    scenes = editor.editable_scenes()
    scenes[0]["title"] = "窗口一"
    assert client.put(URL,json=request(scenes)).status_code == 200
    scenes[0]["title"] = "窗口二"
    assert client.put(URL,json=request(scenes)).status_code == 409
    assert client.get(URL).json()["scenes"][0]["title"] == "窗口一"


def test_atomic_two_writer_conflict(tmp_path):
    database = tmp_path / "race.sqlite3"
    def save_once(number):
        scenes = editor.editable_scenes()
        scenes[0]["title"] = f"修改{number}"
        try:
            return editor.save(editor.SaveDraft.model_validate(request(scenes)), database)["version"]
        except editor.VersionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save_once, [1,2]))
    assert sorted(map(str,results)) == ["1", "conflict"]
    assert len(editor.history(database)) == 2


def test_noop_and_missing_note_rejected(client):
    assert client.put(URL,json=request()).status_code == 422
    scenes = editor.editable_scenes()
    scenes[0]["title"] = "改变标题"
    assert client.put(URL,json=request(scenes,note=" ")).status_code == 422


@pytest.mark.parametrize("mutation", ["duplicate", "reorder", "missing", "extra_source", "bad_id", "empty_narration", "empty_caption", "too_many_captions", "duration_zero"])
def test_malformed_or_evidence_tampering_rejected(client, mutation):
    scenes = editor.editable_scenes()
    if mutation == "duplicate": scenes[1]["scene_id"] = scenes[0]["scene_id"]
    if mutation == "reorder": scenes[0], scenes[1] = scenes[1], scenes[0]
    if mutation == "missing": scenes.pop()
    if mutation == "extra_source": scenes[0]["source_ids"] = ["FORGED"]
    if mutation == "bad_id": scenes[0]["scene_id"] = "../../secret"
    if mutation == "empty_narration": scenes[0]["narration"] = " "
    if mutation == "empty_caption": scenes[0]["subtitle_cards"] = [""]
    if mutation == "too_many_captions": scenes[0]["subtitle_cards"] = ["字幕"]*7
    if mutation == "duration_zero": scenes[0]["duration_seconds"] = 0
    assert client.post(URL+"/analyze",json={"scenes":scenes}).status_code == 422


def test_unsafe_reading_time_can_be_saved_but_not_approved(client):
    scenes = editor.editable_scenes()
    scenes[0]["subtitle_cards"] = ["长"*19, "字幕", "字幕"]
    scenes[0]["duration_seconds"] = 3
    result = client.put(URL,json=request(scenes)).json()
    codes = {issue["code"] for issue in result["analysis"]["scenes"][0]["issues"]}
    assert {"caption_too_long","caption_too_fast","audio_would_be_cut"}.issubset(codes)
    assert result["analysis"]["status"] == "blocked"
    assert result["version"] == 1


def test_duration_only_does_not_require_paid_audio(client):
    scenes = editor.editable_scenes()
    scenes[0]["duration_seconds"] += 1
    data = client.post(URL+"/analyze",json={"scenes":scenes}).json()
    assert data["requires_recomposition"]
    assert not data["requires_science_review"]
    assert data["tts_scene_count"] == 0


def test_version_lookup_and_secret_free_response(client):
    assert client.get(URL+"/versions/9000").status_code == 404
    text = client.get(URL).text.lower()
    assert "api_key" not in text and "authorization" not in text and "sk-ws-" not in text
    assert client.post(URL+"/generate",json={}).status_code in {404,405}
    assert not any(getattr(route,"path","") == URL+"/generate" for route in app.routes)


def long_caption_draft():
    scenes=editor.editable_scenes()
    scenes[2]["subtitle_cards"][0]="耀斑发出的辐射约八分钟后到达地球，可能影响向阳一侧的部分短波通信。"
    return scenes


def test_auto_fix_is_proposal_without_writes_or_generation(client):
    original=long_caption_draft()
    result=client.post(URL+"/auto-fix",json={"scenes":original}).json()
    assert result["stage"]=="proposal_not_applied"
    assert len(result["changes"])==2
    assert {c["field"] for c in result["changes"]}=={"subtitle_cards","duration_seconds"}
    fixed=result["scenes"][2]
    assert "".join(fixed["subtitle_cards"])=="".join(original[2]["subtitle_cards"])
    assert all(len(c)<=18 for c in fixed["subtitle_cards"])
    assert fixed["duration_seconds"]>=len(fixed["subtitle_cards"])*2.5
    assert not editor.store_path().exists()
    assert result["cloud_calls"]==0 and not result["media_updated"]


def test_auto_fix_never_rewrites_scientific_narration(client):
    original=long_caption_draft()
    original[0]["narration"]="所有太阳活动都会让全球网络永久中断。"
    result=client.post(URL+"/auto-fix",json={"scenes":original}).json()
    assert result["scenes"][0]["narration"]==original[0]["narration"]
    assert result["analysis"]["requires_science_review"]
    assert result["analysis"]["status"]!="matches_accepted_media"
    assert result["analysis"]["tts_scene_count"]==1


def test_auto_correction_saved_with_server_verified_provenance(client):
    original=long_caption_draft()
    result=client.post(URL+"/auto-fix",json={"scenes":original}).json()
    payload=request(result["scenes"],note="应用自动字幕拆分与时长修正")
    payload["auto_fix_base"]=original
    response=client.put(URL,json=payload)
    assert response.status_code==200
    saved=response.json()
    assert saved["auto_correction"]["verified_by_server"]
    assert saved["auto_correction"]["stage"]=="applied_to_saved_draft"
    assert saved["auto_correction"]["changes"]==result["changes"]
    assert saved["auto_correction"]["input_sha256"]==result["input_sha256"]
    assert client.get(URL+"/versions/1").json()["auto_correction"]==saved["auto_correction"]


def test_forged_auto_correction_record_is_rejected(client):
    original=long_caption_draft()
    result=client.post(URL+"/auto-fix",json={"scenes":original}).json()
    result["scenes"][0]["narration"]="手动添加的句子。"
    payload=request(result["scenes"])
    payload["auto_fix_base"]=original
    assert client.put(URL,json=payload).status_code==422


def test_auto_fix_six_card_limit_keeps_original_instead_of_deleting_text(client):
    original=editor.editable_scenes()
    original[0]["subtitle_cards"]=["长"*120]
    result=client.post(URL+"/auto-fix",json={"scenes":original}).json()
    assert result["scenes"][0]["subtitle_cards"]==["长"*120]
    assert result["skipped"]
    assert result["analysis"]["has_validation_errors"]


@pytest.mark.parametrize("text", ["短文本", "这是含有完整标点的长文本，必须保证自动拆分后所有字符和标点都完全保留。", "English words and spaces are preserved, even when captions are split."])
def test_split_is_lossless(text):
    pieces=editor._split_caption(text)
    assert pieces is not None
    assert "".join(pieces)==text
    assert all(0<len(p)<=18 for p in pieces)


def test_auto_fix_on_accepted_baseline_is_noop(client):
    original=editor.editable_scenes()
    result=client.post(URL+"/auto-fix",json={"scenes":original}).json()
    assert result["scenes"]==original and result["changes"]==[]
