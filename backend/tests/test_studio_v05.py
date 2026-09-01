"""v0.5 milestone-1 regressions: JSON hardening, deterministic fallback, research
backstops, content sufficiency and in-job media integrity (brief 6.1/6.3/6.4)."""
import asyncio
import json
import wave
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.config import settings
from app.studio_models import ExplanationStep, ProjectInput, RunInput, Source, StudioDraft
from app.services import studio_store as store
from app.services import studio_pipeline as pipeline
from app.services import studio_structured_output as structured
from app.services.studio_fallback import deterministic_cartoon_plan, deterministic_fallback_draft


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIENCE_POSTER_DATA_DIR", str(tmp_path))


def data(topic="为什么月亮会有圆缺变化？", text="月亮本身不发光，我们看到的是它被太阳照亮的侧面。随着月亮绕地球运行，我们看到的明亮部分会从新月变化到满月再到新月。"):
    return ProjectInput(topic=topic, sources=[Source(source_id="S1", title="NASA月亮概念页", text=text)])


def run_input(**kwargs):
    return RunInput(request_id=uuid4(), expected_version=0, **kwargs)


# ---------------------------------------------------------------- JSON hardening

def test_extract_json_object_accepts_fence_and_embedded_and_rejects_ambiguity():
    assert json.loads(structured.extract_json_object("好的，结果如下：\n```json\n{\"a\": 1}\n```")) == {"a": 1}
    assert json.loads(structured.extract_json_object("返回对象：{\"a\": 1} 请查收")) == {"a": 1}
    with pytest.raises(ValueError): structured.extract_json_object("{\"a\": 1} 和 {\"b\": 2} 两个结果")
    with pytest.raises(ValueError): structured.extract_json_object("```json\n{\"a\": 1}\n```\n```json\n{\"b\": 2}\n```")
    with pytest.raises(ValueError): structured.extract_json_object("没有JSON内容")
    with pytest.raises(ValueError): structured.extract_json_object("")


def test_safe_fix_json_only_fixes_trailing_commas():
    assert structured.safe_fix_json('{"a": 1, "b": [1, 2,],}') == '{"a": 1, "b": [1, 2]}'
    payload, note = structured.hardened_json('{"a": 1,}')
    assert payload == {"a": 1} and note.startswith("trailing_comma_fixed")
    with pytest.raises(ValueError): structured.hardened_json('{"a" 1}')


def test_repair_known_aliases_copies_missing_fields_only():
    raw = {"scenes": [{"id": "V1", "narration_text": "这段文字作为旁白使用，长度足够。", "title": "标题", "visual": "画面描述文字", "claim_ids": ["C1"]}],
           "claims": [{"id": "C1", "text": "事实", "source_id": "S1", "quote": "这是足够长的原文引文用于测试。", "boundary": "边界"}]}
    changed = structured.repair_known_aliases(raw)
    assert raw["scenes"][0]["scene_id"] == "V1"
    assert raw["scenes"][0]["narration"] == "这段文字作为旁白使用，长度足够。"
    assert raw["scenes"][0]["heading"] == "标题"
    assert raw["scenes"][0]["visual_action"] == "画面描述文字"
    assert raw["claims"][0]["claim_id"] == "C1"
    assert len(changed) == 5
    before = {"scene_id": "V1", "id": "V2"}
    structured.repair_known_aliases(before)
    assert before["scene_id"] == "V1"  # existing values are never overwritten


def test_studio_json_accepts_fenced_output_and_records_hardening(monkeypatch):
    from app.services.qwen_client import QwenClient
    body = {"id": "test-1", "model": "qwen3-max",
            "choices": [{"message": {"content": "```json\n{\"title\": \"月亮\", \"claims\": [], \"scenes\": []}\n```"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}

    class FakeResponse:
        def json(self): return body
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr("app.services.qwen_client.httpx.AsyncClient", FakeClient)
    client = QwenClient(replace(settings, mock_ai=False, dashscope_api_key="test-key",
                                qwen_text_model="qwen3-max", qwen_studio_model="qwen3-max"))
    payload, receipt = asyncio.run(client.studio_json("prompt", {"x": 1}, "test_purpose"))
    assert payload["title"] == "月亮"
    assert receipt["json_hardening"] == "code_block"
    assert receipt["purpose"] == "test_purpose"


# ---------------------------------------------------------------- deterministic fallback

def test_deterministic_fallback_is_valid_and_evidence_clean():
    project_data = data()
    draft, reason = deterministic_fallback_draft(project_data,
        primer_answer="月亮本身不发光，月光来自太阳的反射。随着月球绕地球公转，太阳照亮的半球以不同角度朝向地球，所以我们看到的新月、上弦月、满月、下弦月组成一个完整周期。")
    assert "模板" in reason
    assert len(draft.scenes) == 6
    roles = {s.role for s in draft.scenes}
    assert {"hook", "example", "mechanism", "boundary", "takeaway"}.issubset(roles)
    assert pipeline.validate_evidence(draft, project_data) == []
    narrations = [pipeline.normalized(s.narration) for s in draft.scenes]
    assert len(set(narrations)) == 6
    assert sum(len(s.narration) for s in draft.scenes) >= 180
    assert all(len(s.narration) <= 90 for s in draft.scenes)
    assert draft.diagram.labels == [n.label for n in draft.public_poster.nodes]
    issues = pipeline.validate_communication(draft, project_data)
    assert all(f["severity"] != "blocker" for f in issues)


def test_generation_falls_back_to_template_and_marks_version():
    project = store.create_project(data())
    invalid = {"scenes": [{"scene_id": "V1"}], "claims": []}
    no_change = {"findings": [], "revised": None}
    responses = [invalid, invalid, no_change, no_change]
    calls = []
    async def model(prompt, payload, purpose):
        calls.append(purpose)
        return responses.pop(0), {"model": "qwen-test", "purpose": purpose, "request_id": "test-only"}
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert len(result["versions"]) == 2
    first = result["versions"][0]
    assert first["fallback"] is True
    assert "本地确定性6镜模板" in first["fallback_reason"]
    assert first["findings"] == []
    assert len(StudioDraft.model_validate(first["draft"]).scenes) == 6
    assert calls[:2] == ["studio_generate", "studio_generate_schema_repair"]
    assert calls[2:] == ["studio_review_rewrite", "studio_recheck"]
    assert result["versions"][1]["review_status"] == "ai_checked_human_pending"
    assert not responses


def test_generation_falls_back_when_repair_call_itself_fails():
    project = store.create_project(data())
    invalid = {"scenes": [{"scene_id": "V1"}], "claims": []}
    no_change = {"findings": [], "revised": None}
    responses = [invalid, no_change, no_change]
    async def model(prompt, payload, purpose):
        if purpose == "studio_generate_schema_repair":
            raise ValueError("模型输出被截断，未保存不完整作品")
        return responses.pop(0), {}
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert result["versions"][0]["fallback"] is True
    assert result["runs"][-1]["state"] == "succeeded"


def test_deterministic_cartoon_plan_matches_scenes_and_icons():
    from app.services.studio_cartoon import ICONS
    draft, _ = deterministic_fallback_draft(data())
    plan = deterministic_cartoon_plan(draft)
    assert [s.scene_id for s in plan.scenes] == [s.scene_id for s in draft.scenes]
    assert all(a.icon in ICONS for s in plan.scenes for a in s.actors)
    assert all(8 <= len(s.caption) <= 48 for s in plan.scenes)


def test_deterministic_cartoon_plan_uses_topic_objects_without_claiming_qwen():
    draft = pipeline.mock_draft(data())
    draft.scenes[0].heading = "月亮为什么有圆缺？"
    draft.scenes[0].narration = "太阳照亮月亮，我们从地球看到的亮面比例随位置变化。"
    draft.scenes[0].visual_action = "用太阳、月亮和地球展示相对位置。"
    scene = deterministic_cartoon_plan(draft).scenes[0]
    assert {actor.icon for actor in scene.actors} == {"sun", "moon", "earth"}
    assert "模板" in scene.caption


# ---------------------------------------------------------------- research backstops

def test_domain_backstops_are_public_https():
    from app.services.studio_research import DOMAIN_BACKSTOPS, safe_public_url
    assert DOMAIN_BACKSTOPS["science"][0][0] == "月亮"
    for domain, entries in DOMAIN_BACKSTOPS.items():
        for term, url, title in entries:
            assert term and url.startswith("https://")
            assert title and len(title) <= 60
            assert safe_public_url(url) == url


def test_question_split_and_expansion_are_bounded():
    from app.services.studio_research import Primer, split_question, expansion_query, ambiguous_backstops, passage_chunks
    parts = split_question("为什么月亮有圆缺变化，又为什么有时亮一些？")
    assert parts and len(parts) == 1 and 2 <= len(parts[0]) <= 30
    primer = Primer(domain="science", answer="月亮本身不发光，月光来自太阳的反射。我们看到的明亮部分随月亮绕地球运行而变化。",
                    queries=["月亮 圆缺 官方", "moon phases official documentation"])
    query = expansion_query(primer, "月亮为什么会有圆缺变化？")
    assert len(query) <= 240 and "机制" in query
    assert len(ambiguous_backstops("什么是token")) == 2
    assert ambiguous_backstops("Token Plan怎么买") == []
    wrapped = "Access tokens are credentials used to access protected resources.\nAn access token is a string representing an authorization issued to the client.\nThe string is usually opaque to the client."
    chunks = passage_chunks(wrapped)
    assert chunks and "protected resources" in chunks[0] and "opaque" in chunks[0]


def test_warning_only_review_finishes_run_for_automatic_media():
    project = store.create_project(data())
    draft = pipeline.mock_draft(data())
    warning = {"target": "wording", "severity": "warning", "message": "人工终审时留意表达。"}
    responses = [draft.model_dump(), {"findings": [warning], "revised": draft.model_dump()},
                 {"findings": [warning], "revised": None},
                 {"findings": [warning], "revised": draft.model_dump()},
                 {"findings": [warning], "revised": None}]
    async def model(prompt, payload, purpose):
        return responses.pop(0), {"purpose": purpose}
    request = run_input(make_video=True)
    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(
            pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    assert result["versions"][-1]["review_status"] == "needs_human_review"
    assert result["runs"][-1]["state"] == "succeeded"


def test_review_findings_without_revision_trigger_one_forced_rewrite():
    project_data = data()
    project = store.create_project(project_data)
    draft = pipeline.mock_draft(project_data)
    revised = draft.model_copy(deep=True)
    revised.scenes[0].heading = "已实际修改"
    finding = {"target": "V1", "severity": "warning", "message": "需要改写。"}
    responses = [draft.model_dump(), {"findings": [finding], "revised": None},
                 {"findings": [], "revised": revised.model_dump()}, {"findings": [], "revised": None}]
    purposes = []
    async def model(prompt, payload, purpose):
        purposes.append(purpose)
        return responses.pop(0), {"purpose": purpose}
    request = run_input()
    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(
            pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    assert "studio_review_forced_rewrite" in purposes
    assert result["versions"][-1]["draft"]["scenes"][0]["heading"] == "已实际修改"
    assert result["runs"][-1]["state"] == "succeeded"


def test_research_uses_backstop_and_verifies_fetch(monkeypatch):
    from app.services import studio_research as research
    from app.services.studio_research import Primer
    primer = Primer(domain="science", answer="月亮本身不发光，月光来自太阳的反射，随月球绕地球运行而周期性地变化。",
                    queries=["月亮 圆缺 官方", "moon phases official"])
    async def fake_orient(client, question):
        return primer, {"purpose": "orient"}
    async def fake_search(client, query, restricted=True, sites=None):
        return [], {"purpose": "search"}
    page = {"url": "https://science.nasa.gov/moon/", "title": "NASA Moon",
            "text": "月亮本身不发光。月亮绕地球运行，我们看到被太阳照亮的侧面随时间变化，形成新月、上弦、满月和下弦。月球的公转周期约为二十七天。"}
    async def fake_fetch(url):
        return page["url"], page["text"]
    class FakeClient:
        async def studio_json(self, prompt, payload, purpose):
            if purpose == "studio_source_selection":
                return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"], "reason": "直接解释月亮圆缺"}], "gap": ""}, {}
            return {"domain": "science"}, {}
    monkeypatch.setattr(research, "orient", fake_orient)
    monkeypatch.setattr(research, "search", fake_search)
    monkeypatch.setattr(research, "fetch_page", fake_fetch)
    result = asyncio.run(research.research(FakeClient(), "月亮为什么会有圆缺变化？", lambda label: None))
    assert result["sources"] and result["sources"][0]["url"] == "https://science.nasa.gov/moon/"
    assert any(e["state"] == "原文已提取" for e in result["events"])


# ---------------------------------------------------------------- content sufficiency

def test_thin_narration_and_short_explainer_get_warnings():
    p = data()
    draft = pipeline.mock_draft(p)
    for scene in draft.scenes:
        scene.narration = "这段旁白太短了。"
    issues = pipeline.validate_communication(draft, p)
    assert any(i["target"] == "scenes.narration" and "不足180字" in i["message"] for i in issues)


def test_explainer_short_body_and_coverage_warnings():
    p = data()
    draft = pipeline.mock_draft(p)
    draft.explainer = [ExplanationStep(heading="简短", body="这篇讲解只说了一句话，剩下的部分都用重复的措辞来填充，没有真正展开任何内容，也没有给出更具体的说明。", claim_ids=["C1"])]
    issues = pipeline.validate_communication(draft, p)
    assert any(i["target"] == "explainer" and "过短" in i["message"] for i in issues)
    assert any(i["target"] == "explainer" and "缺少" in i["message"] for i in issues)


# ---------------------------------------------------------------- media integrity

def test_verify_media_output_decodes_video_and_frames(tmp_path, monkeypatch):
    from app.services import studio_video as video
    from PIL import Image
    draft = pipeline.mock_draft(data())
    image = tmp_path / "frame.png"
    Image.new("RGB", (1280, 720), "#08252f").save(image)
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(b"\0\0" * 6000)
    real_combine = video.combine_audio
    def fast_combine(paths, target, pad):
        return real_combine(paths, target, 0)
    monkeypatch.setattr(video, "combine_audio", fast_combine)
    plans = [{"scene_id": s.scene_id, "relationship": "reveal", "caption": "按已有资料展示主要对象及关系。",
              "actors": [{"icon": "book", "label": "资料", "explanation": "先查看已有的证据"},
                         {"icon": "person", "label": "公众", "explanation": "再解释知识的含义"}]} for s in draft.scenes]
    video.compose(draft, [image] * 6, [voice] * 6, tmp_path, cartoon_plans=plans)
    integrity = video.verify_media_output(tmp_path)
    assert integrity["status"] == "ok"
    assert integrity["has_audio"] is True and integrity["duration_seconds"] > 0
    assert len(integrity["sample_frames"]) == 3
    assert integrity["sample_positions_seconds"] == [
        round(integrity["duration_seconds"] * fraction, 3) for fraction in (0.25, 0.5, 0.75)]
    assert integrity["subtitles"]["status"] == "ok"
    for name in integrity["sample_frames"]:
        assert (tmp_path / name).stat().st_size > 0


def test_verify_media_output_rejects_garbage(tmp_path):
    from app.services import studio_video as video
    (tmp_path / "preview.mp4").write_bytes(b"this is not a video")
    integrity = video.verify_media_output(tmp_path)
    assert integrity["status"] == "failed"


def test_verify_subtitles_rejects_fragment_and_accepts_wrapped_sentence(tmp_path):
    from app.services.studio_video import verify_subtitles
    path = tmp_path / "subtitles.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\n这是一个完整\n句子。\n", encoding="utf-8")
    assert verify_subtitles(path, 2)["status"] == "ok"
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\n这是半句\n", encoding="utf-8")
    result = verify_subtitles(path, 2)
    assert result["status"] == "failed" and result["incomplete_cues"] == [1]


def test_wrap_pixels_never_leaves_closing_punctuation_on_its_own_line():
    from app.services.studio_video import wrap_pixels

    class FixedFont:
        @staticmethod
        def getlength(value):
            return len(value)

    lines = wrap_pixels("这是完整的一句话。", FixedFont(), 8)
    assert lines == ["这是完整的一句话。"]
    assert all(line not in {"。", "，", "！", "？"} for line in lines)


def test_research_science_backstop_sky_maps_to_nasa_space_place(monkeypatch):
    from app.services import studio_research as research
    from app.services.studio_research import Primer
    primer = Primer(domain="science", answer="天空呈蓝色、夕阳呈红色，都是因为阳光穿过大气时发生散射。蓝光波长较短，更容易被空气分子散射到各个方向，所以白天天空是蓝色的。",
                    queries=["天空 蓝色 官方", "sunset red official"])
    async def fake_orient(client, question):
        return primer, {"purpose": "orient"}
    async def fake_search(client, query, restricted=True, sites=None):
        return [], {"purpose": "search"}
    page = {"url": "https://spaceplace.nasa.gov/blue-sky/en/", "title": "NASA Space Place：天空为什么是蓝色",
            "text": "阳光穿过大气层时会被空气中的气体分子散射。蓝光波长最短，被散射得最厉害，所以我们看到的天空是蓝色的。日出日落时阳光斜穿更厚的大气，蓝光被散射殆尽，剩下红光直达眼睛，太阳因此呈红色。"}
    async def fake_fetch(url):
        return page["url"], page["text"]
    class FakeClient:
        async def studio_json(self, prompt, payload, purpose):
            if purpose == "studio_source_selection":
                return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"], "reason": "直接解释天空颜色成因"}], "gap": ""}, {}
            return {"domain": "science"}, {}
    monkeypatch.setattr(research, "orient", fake_orient)
    monkeypatch.setattr(research, "search", fake_search)
    monkeypatch.setattr(research, "fetch_page", fake_fetch)
    result = asyncio.run(research.research(FakeClient(), "为什么天空是蓝色的，而夕阳是红色的？", lambda label: None))
    assert result["sources"] and result["sources"][0]["url"] == "https://spaceplace.nasa.gov/blue-sky/en/"
    assert any(e["state"] == "原文已提取" for e in result["events"])


def test_research_strips_tracking_query_before_fetch(monkeypatch):
    from app.services import studio_research as research
    from app.services.studio_research import Primer
    primer = Primer(domain="education", answer="间隔复习指把学习内容分开安排，中间隔一段时间，比一次性集中学习更有利于长期记忆。间隔一段时间复习关键内容是一种有效的教学安排。",
                    queries=["学习方法 官方", "study skills university"])
    async def fake_orient(client, question):
        return primer, {"purpose": "orient"}
    async def fake_search(client, query, restricted=True, sites=None):
        return [{"url": "https://ies.ed.gov/ncee/wwc/PracticeGuide/1?utm_source=qwen&utm_medium=test",
                 "title": "IES Practice Guide"}], {"purpose": "search"}
    page = {"url": "https://ies.ed.gov/ncee/wwc/PracticeGuide/1", "title": "IES Practice Guide",
            "text": "间隔复习指把学习内容分开安排，中间隔一段时间，比一次性集中学习更有利于长期记忆。间隔一段时间复习关键内容是一种有效的教学安排。"}
    async def fake_fetch(url):
        return page["url"], page["text"]
    class FakeClient:
        async def studio_json(self, prompt, payload, purpose):
            if purpose == "studio_source_selection":
                return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"], "reason": "直接解释间隔复习"}], "gap": ""}, {}
            return {"domain": "education"}, {}
    monkeypatch.setattr(research, "orient", fake_orient)
    monkeypatch.setattr(research, "search", fake_search)
    monkeypatch.setattr(research, "fetch_page", fake_fetch)
    result = asyncio.run(research.research(FakeClient(), "间隔复习为什么有效？", lambda label: None))
    assert result["sources"] and result["sources"][0]["url"] == "https://ies.ed.gov/ncee/wwc/PracticeGuide/1"
    assert not any("跳过" in e["state"] for e in result["events"])
