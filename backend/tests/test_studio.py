import asyncio
from dataclasses import replace
import io
import json
from unittest.mock import patch
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.config import settings
from app.studio_models import ProjectInput, Source, RunInput
from app.services import studio_store as store
from app.services import studio_pipeline as pipeline
from app.services.model_policy import validate_model_policy
from app.services.studio_export import export_zip, poster_svg


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIENCE_POSTER_DATA_DIR", str(tmp_path))


def data(topic="测试科学主题", text="这是一段用于测试原文定位的资料，只有在对应条件成立时才适用。"):
    return ProjectInput(topic=topic, sources=[Source(source_id="S1", title="测试来源", text=text)])


def run_input(version=0, **kwargs):
    return RunInput(request_id=uuid4(), expected_version=version, **kwargs)


def test_sources_are_isolated_and_immutable():
    a = store.create_project(data("第一主题"))
    b = store.create_project(data("第二主题", "第二份资料与第一份资料独立保存，不会共享或污染证据引用。"))
    assert a["id"] != b["id"]
    assert "第二份" not in store.get_project(a["id"])["input"]["sources"][0]["text"]
    assert len(store.list_projects()) == 2


def test_rejects_invalid_quote_and_unknown_claim():
    p = data()
    draft = pipeline.mock_draft(p)
    assert pipeline.validate_evidence(draft, p) == []
    draft.claims[0].quote = "捏造的一段原文，引文应无法定位"
    draft.scenes[0].claim_ids = ["C9"]
    assert len(pipeline.validate_evidence(draft, p)) == 2


def test_original_source_id_is_required_even_when_quote_matches_elsewhere():
    p = data()
    draft = pipeline.mock_draft(p)
    draft.claims[0].source_id = "S2"
    assert pipeline.validate_evidence(draft, p)[0]["severity"] == "blocker"


def test_caption_split_is_lossless():
    text = "这是一段很长的旁白，需要切分为便于阅读的字幕，但是不能丢失任何字和标点。" * 5
    cards = pipeline.subtitle_cards(text)
    assert "".join(cards) == text
    assert all(len(card) <= 18 for card in cards)


def test_reservation_deduplicates_and_checks_version():
    project = store.create_project(data())
    r = run_input()
    assert store.reserve(project["id"], r)
    assert not store.reserve(project["id"], r)
    with pytest.raises(ValueError):
        store.reserve(project["id"], run_input())
    store.stage(r.request_id, "done", "succeeded")
    store.append_version(project["id"], {"draft": {}})
    with pytest.raises(ValueError):
        store.reserve(project["id"], run_input())
    assert store.reserve(project["id"], run_input(1))


def test_request_id_cannot_be_reused_for_different_project_or_feedback():
    a, b = store.create_project(data()), store.create_project(data())
    r = run_input()
    store.reserve(a["id"], r)
    with pytest.raises(ValueError):
        store.reserve(b["id"], r)
    with pytest.raises(ValueError):
        store.reserve(a["id"], r.model_copy(update={"feedback": "different"}))


def test_no_sources_never_calls_model_or_solar_retrieval():
    project = store.create_project(ProjectInput(topic="没有资料的问题"))
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline.QwenClient, "studio_json", side_effect=AssertionError("no cloud")):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert result["runs"][-1]["state"] == "blocked"
    assert not result["versions"]


def test_mock_is_explicit_and_exports_escape_html():
    project = store.create_project(data("<script>恶意标题</script>"))
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=True)):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert result["versions"][0]["mode"] == "mock"
    assert not result["versions"][0]["calls"]
    result["versions"][0]["draft"]["title"] = "<script>x</script>"
    assert "<script>" not in poster_svg(result)
    with zipfile.ZipFile(io.BytesIO(export_zip(result))) as archive:
        assert "poster.svg" in archive.namelist()
        assert ".env" not in archive.namelist()
        assert "<script>" not in archive.read("index.html").decode()
        assert "功能演示" in archive.read("poster.svg").decode()


def test_automatic_rewrite_is_applied_and_rechecked():
    project = store.create_project(data())
    draft = pipeline.mock_draft(data()).model_dump()
    revised = json.loads(json.dumps(draft))
    revised["scenes"][0]["narration"] = "我们从一个生活中的问题出发，看看资料能够告诉我们什么。"
    responses = [draft, {"findings": [{"target": "V1", "severity": "warning", "message": "旁白不够通俗"}], "revised": revised}, {"findings": [], "revised": None}]
    async def model(*args):
        return responses.pop(0), {"model": "qwen-test", "purpose": args[-1], "request_id": "test-only"}
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert len(result["versions"]) == 2
    assert result["versions"][0]["draft"] == draft
    assert result["versions"][1]["draft"] == revised
    assert result["versions"][1]["changes"][0]["field"] == "scenes[1].narration"
    assert result["versions"][1]["review_status"] == "ai_checked_human_pending"
    assert not responses


def test_bad_revision_does_not_replace_original():
    project = store.create_project(data())
    draft = pipeline.mock_draft(data()).model_dump()
    revised = json.loads(json.dumps(draft))
    revised["claims"][0]["quote"] = "这是一条不存在于原文里的虚构引文，不应通过。"
    responses = [draft, {"findings": [], "revised": revised}]
    async def model(*args): return responses.pop(0), {}
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert result["versions"][-1]["draft"] == draft
    assert result["versions"][-1]["proposed_changes"]
    assert result["runs"][-1]["state"] == "blocked"


def test_recheck_warning_triggers_second_round_without_human_click():
    project = store.create_project(data())
    draft = pipeline.mock_draft(data()).model_dump()
    first = json.loads(json.dumps(draft))
    first["takeaway"] = "先从资料的原句出发，看看它实际能证明哪些内容。"
    second = json.loads(json.dumps(first))
    second["scenes"][1]["narration"] = "换个简单的问题，我们先看资料中有哪些确切的证据。"
    warning = {"target": "V2", "severity": "warning", "message": "请继续简化旁白"}
    responses = [draft, {"findings": [], "revised": first}, {"findings": [warning], "revised": None},
                 {"findings": [warning], "revised": second}, {"findings": [], "revised": None}]
    async def model(*args): return responses.pop(0), {}
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert len(result["versions"]) == 3
    assert result["versions"][-1]["iteration"] == 2
    assert result["versions"][-1]["draft"] == second
    assert result["runs"][-1]["state"] == "succeeded"
    assert not responses


def test_second_round_warning_finishes_with_human_review_without_infinite_retry():
    project = store.create_project(data())
    draft = pipeline.mock_draft(data()).model_dump()
    warning = {"target": "V2", "severity": "warning", "message": "仍需人工检查"}
    responses = [draft] + [{"findings": [warning], "revised": None}] * 4
    async def model(*args): return responses.pop(0), {}
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert len(result["versions"]) == 3
    assert result["versions"][-1]["review_status"] == "needs_human_review"
    assert result["runs"][-1]["state"] == "succeeded"
    assert not responses


def test_failure_preserves_initial_version_and_sanitizes_error():
    project = store.create_project(data())
    draft = pipeline.mock_draft(data()).model_dump()
    responses = [draft]
    async def model(*args):
        if responses: return responses.pop(), {}
        raise RuntimeError("private provider response must not be exposed")
    r = run_input()
    store.reserve(project["id"], r)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], r))
    result = store.get_project(project["id"])
    assert len(result["versions"]) == 1
    assert result["runs"][-1]["state"] == "failed"
    assert "private provider" not in json.dumps(result)


def test_invalid_review_candidate_is_ignored_and_second_round_can_recover():
    source = data()
    project = store.create_project(source)
    old = pipeline.mock_draft(source).model_dump()
    old["scenes"][0]["narration"] = "第一天学、第三天测，第十天再看，让大脑巩固长期记忆。"
    store.append_version(project["id"], {"mode": "bailian", "draft": old, "review_status": "blocked"})
    invalid = json.loads(json.dumps(old))
    invalid["explainer"] = [{"heading": "结构不完整", "body": "太短了", "claim_ids": ["C1"]}]
    repaired = json.loads(json.dumps(old))
    repaired["scenes"][0]["narration"] = "先根据资料说清能确认的做法，来源没有解释的机制不作结论。"
    responses = [
        {"findings": [], "revised": invalid},
        {"findings": [], "revised": invalid},
        {"findings": [], "revised": repaired},
        {"findings": [], "revised": None},
    ]
    async def model(*args): return responses.pop(0), {"purpose": args[-1]}
    request = run_input(1)
    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    print("DEBUG run state:", result["runs"][-1]["state"], "| stage:", (result["runs"][-1].get("stage") or "")[:60], "| error:", (result["runs"][-1].get("error") or "")[:200])
    assert result["runs"][-1]["state"] == "succeeded"
    assert result["versions"][-1]["draft"]["scenes"][0]["narration"] == repaired["scenes"][0]["narration"]
    assert not responses


@pytest.mark.parametrize("url", ["http://example.com", "https://user:password@example.com", "https://example.com/?signature=x", "javascript:alert(1)"])
def test_source_urls_reject_credentials_or_active_content(url):
    with pytest.raises(ValidationError): Source(source_id="S1", title="资料", text="这是长度足够用于测试的一段资料文本，不含任何科学论断。", url=url)


@pytest.mark.parametrize("model", ["gpt-4", "deepseek-chat", "wan2.6"])
def test_text_model_policy_rejects_other_families(model):
    with pytest.raises(RuntimeError): validate_model_policy(replace(settings, qwen_text_model=model))


@pytest.mark.parametrize("url", ["https://attacker.example/compatible-mode/v1", "http://dashscope.aliyuncs.com", "https://dashscope.aliyuncs.com.evil.test", "https://llm-test.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"])
def test_endpoint_policy_rejects_unapproved_host(url):
    with pytest.raises(RuntimeError): validate_model_policy(replace(settings, dashscope_base_url=url))


def test_source_size_and_duplicate_ids_rejected():
    with pytest.raises(ValidationError): ProjectInput(topic="重复来源", sources=[data().sources[0], data().sources[0]])
    with pytest.raises(ValidationError): Source(source_id="S1", title="太长资料", text="字" * 15001)


def test_api_uses_safe_ids_and_export_requires_version():
    with TestClient(app) as client:
        assert client.get("/api/studio/projects/not-a-uuid").status_code == 422
        p = client.post("/api/studio/projects", json=data().model_dump()).json()
        assert client.get(f"/api/studio/projects/{p['id']}/export").status_code == 409
        assert client.get(f"/api/studio/projects/{p['id']}").status_code == 200
        assert client.get(f"/api/studio/projects/{uuid4()}").status_code == 404


def test_restart_recovers_interrupted_state_without_touching_versions():
    p = store.create_project(data())
    store.reserve(p["id"], run_input())
    store.append_version(p["id"], {"draft": {}})
    store.recover_interrupted_runs()
    result = store.get_project(p["id"])
    assert result["runs"][0]["state"] == "failed"
    assert len(result["versions"]) == 1


def test_rejected_final_revision_falls_back_to_accepted_version_without_blocking():
    source = data()
    project = store.create_project(source)
    base = pipeline.mock_draft(source).model_dump()
    clean = json.loads(json.dumps(base))
    clean["scenes"][0]["narration"] = "按资料说明的做法复习：把关键内容安排在初次学习后隔一段时间再回顾。"
    clean["scenes"][1]["narration"] = clean["scenes"][0]["narration"]  # duplicate keeps a warning so round 2 runs
    bad = json.loads(json.dumps(base))
    bad["scenes"][0]["narration"] = "第一天学、第三天测，第十天再看，让大脑巩固长期记忆。"
    store.append_version(project["id"], {"mode": "bailian", "draft": base, "review_status": "pending"})
    responses = [
        {"findings": [], "revised": clean},   # round 1 revision accepted
        {"findings": [], "revised": None},    # round 1 recheck
        {"findings": [], "revised": bad},     # round 2 revision reintroduces blocker
        {"findings": [], "revised": None},    # round 2 recheck
    ]
    async def model(*args): return responses.pop(0), {"purpose": args[-1]}
    request = run_input(1)
    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    assert result["runs"][-1]["state"] == "succeeded"
    assert "沿用本轮已审核通过的版本" in result["runs"][-1]["stage"]
    latest = result["versions"][-1]
    assert latest["review_status"] == "blocked"  # rejection is recorded, nothing overwritten
    assert latest["draft"]["scenes"][0]["narration"] == clean["scenes"][0]["narration"]
    assert any(f["severity"] == "blocker" for f in latest["findings"])
    assert not responses


def test_primer_fallback_generates_video_when_research_finds_no_pages():
    # User decision: when no public page can be fetched and verified, the AI preliminary
    # answer becomes the sole labelled content basis instead of blocking the run.
    from app.services import studio_research as research_mod
    from app.studio_models import ProjectInput, Source
    project = store.create_project(ProjectInput(topic="为什么天空是蓝色的？", audience="普通公众", sources=[], auto_sources=True))
    request = run_input(0)
    primer = "天空呈蓝色、夕阳呈红色，都是因为阳光穿过大气时发生的瑞利散射。蓝光波长较短，更容易被空气中的分子散射到各个方向，所以白天我们看到整个天空是蓝色的。"
    snapshot = {"sources": [], "gap": "暂未找到可读取且能直接支持该问题的可信资料。系统已自动尝试同义词、官方机构、高校与专业组织来源。",
                "explanation": {"answer": primer, "domain": "science", "queries": ["天空 蓝色 原理"], "status": "model_background_unverified"},
                "events": [{"url": "", "state": "跳过：来源域名或URL安全规则不满足"}], "calls": [], "selected": []}
    primer_input = ProjectInput.model_validate({"topic": "为什么天空是蓝色的？", "audience": "普通公众", "auto_sources": True, "sources": [{
        "source_id": "S1", "title": "AI初步解释（未找到可核对网页，内容未经外部来源核实）", "url": "", "text": primer}]})
    base = pipeline.mock_draft(primer_input).model_dump()
    responses = [
        base,                                # generate: real model returns a bare draft
        {"findings": [], "revised": None},   # round 1 review: keep base draft
        {"findings": [], "revised": None},   # round 1 recheck
    ]
    async def model(*args):
        purpose = args[-1]
        if purpose == "studio_rebuild":
            return base, {"purpose": purpose}
        return responses.pop(0), {"purpose": purpose}

    async def fake_research(client, topic, progress):
        progress("读取公开原文（已获得0份，最多6份）")
        return snapshot

    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(research_mod, "research", new=fake_research), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    assert result["runs"][-1]["state"] == "succeeded"
    latest = result["versions"][-1]
    assert latest["review_status"] != "blocked"
    assert latest["draft"]["claims"][0]["source_id"] == "S1"
    assert "AI初步解释" in latest["draft"]["claims"][0]["quote"] or all(
        c["quote"] in primer for c in latest["draft"]["claims"])
    assert any("AI初步解释" in v.get("fallback_reason", "") for v in result["versions"])


def test_blocked_first_round_still_blocks_run_when_no_accepted_version_exists():
    source = data()
    project = store.create_project(source)
    base = pipeline.mock_draft(source).model_dump()
    bad = json.loads(json.dumps(base))
    bad["scenes"][0]["narration"] = "第一天学、第三天测，第十天再看，让大脑巩固长期记忆。"
    store.append_version(project["id"], {"mode": "bailian", "draft": base, "review_status": "pending"})
    responses = [
        {"findings": [], "revised": bad},     # round 1 revision has blocker
        {"findings": [], "revised": None},    # round 1 recheck
        {"findings": [], "revised": bad},     # round 2 still bad
        {"findings": [], "revised": None},    # round 2 recheck
    ]
    async def model(*args): return responses.pop(0), {"purpose": args[-1]}
    request = run_input(1)
    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    assert result["runs"][-1]["state"] == "blocked"
    assert result["runs"][-1]["stage"] == "正在补充可靠资料"


def test_stale_zero_source_research_is_rerun_not_reused():
    # A project whose stored research snapshot has zero sources (old failure or old
    # code) must trigger a fresh search on re-run instead of reusing the dead end.
    from app.services import studio_research as research_mod
    from app.studio_models import ProjectInput, Source
    project = store.create_project(ProjectInput(topic="为什么天空是蓝色的？", audience="普通公众", sources=[], auto_sources=True))
    stale = {"sources": [], "gap": "暂未找到可读取且能直接支持该问题的可信资料。",
             "explanation": {"answer": "旧的初步回答。", "domain": "science", "queries": ["天空 蓝色"], "status": "model_background_unverified"},
             "events": [], "calls": [], "selected": []}
    store.save_research(project["id"], stale)
    request = run_input(0)
    fresh_text = "阳光穿过大气层时会被空气中的气体分子散射。蓝光波长较短，被散射得最厉害，所以我们看到的天空是蓝色的。"
    fresh = {"sources": [{"source_id": "S1", "title": "NASA Space Place：天空为什么是蓝色",
                          "url": "https://spaceplace.nasa.gov/blue-sky/en/", "text": fresh_text}],
             "gap": "", "explanation": {"answer": "阳光穿过大气层时会被空气分子散射，蓝光波长较短被散射得最厉害，所以天空呈蓝色；夕阳时阳光斜穿更厚的大气，蓝光被散射殆尽，剩下红光直达眼睛。", "domain": "science", "queries": ["天空 蓝色"], "status": "model_background_unverified"},
             "events": [{"url": "https://spaceplace.nasa.gov/blue-sky/en/", "state": "原文已提取"}], "calls": [], "selected": []}
    base = pipeline.mock_draft(ProjectInput.model_validate({"topic": "为什么天空是蓝色的？", "audience": "普通公众", "auto_sources": True, "sources": [
        {"source_id": "S1", "title": "NASA Space Place：天空为什么是蓝色", "url": "https://spaceplace.nasa.gov/blue-sky/en/", "text": fresh_text}]})).model_dump()
    responses = [base] + [{"findings": [], "revised": None}] * 4
    async def model(*args):
        return responses.pop(0), {"purpose": args[-1]}
    searched = []
    async def fake_research(client, topic, progress):
        searched.append(topic)
        return fresh
    store.reserve(project["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(research_mod, "research", new=fake_research), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(project["id"], request))
    result = store.get_project(project["id"])
    assert searched == ["为什么天空是蓝色的？"], "0-source snapshot must trigger a fresh research run"
    assert result["runs"][-1]["state"] == "succeeded"
    assert result["versions"][-1]["draft"]["claims"][0]["source_id"] == "S1"
    assert not any(v.get("fallback_reason", "").startswith("未找到可核对的公开网页") for v in result["versions"])
