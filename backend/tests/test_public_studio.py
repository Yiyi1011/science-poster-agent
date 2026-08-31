import asyncio
from dataclasses import replace
import json
from unittest.mock import patch
from uuid import uuid4
from xml.etree import ElementTree as ET

import httpx
import pytest
from pydantic import ValidationError

from app.config import settings
from app.studio_models import ProjectInput, Source, StudioDraft, RunInput
from app.services import studio_pipeline as pipeline, studio_store as store
from app.services import studio_research as research
from app.services.public_poster import wrap, render
from app.services.studio_export import poster_svg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIENCE_POSTER_DATA_DIR", str(tmp_path))
    async def orientation(*args):
        return research.Primer(domain="science", answer="这是一段仅供测试的模型初步解释，不可用作原始文献资料或者已经核实的来源。", queries=["query1", "query2"]), {}
    monkeypatch.setattr(research, "orient", orientation)


def data():
    return ProjectInput(topic="科学问题", sources=[Source(source_id="S1", title="测试资料", text="这是一段用于验证数据结构的资料，只有在对应条件成立时才能应用结论。")])


def test_legacy_three_scene_versions_remain_readable():
    draft = pipeline.mock_draft(data()).model_dump()
    draft.pop("public_poster")
    draft["scenes"] = draft["scenes"][:3]
    for s in draft["scenes"]: s.pop("role")
    parsed = StudioDraft.model_validate(draft)
    assert parsed.public_poster is None
    project = {"input": data().model_dump(), "versions": [{"version": 1, "mode": "mock", "draft": draft}]}
    ET.fromstring(poster_svg(project))
    assert any(f["target"] == "scenes" for f in pipeline.validate_communication(parsed))


def test_new_public_schema_is_traceable_and_readability_checked():
    draft = pipeline.mock_draft(data())
    assert not pipeline.validate_communication(draft)
    draft.public_poster.cards[0].claim_ids = ["C99"]
    draft.public_poster.nodes[0].claim_ids = ["C88"]
    assert len(pipeline.validate_evidence(draft, data())) == 2
    draft.public_poster.cards[0].body = "这里出现confabulation以及一个过长的英文术语。"
    draft.scenes[0].narration = "很长的旁白" * 30
    draft.scenes[1].narration = draft.scenes[0].narration
    draft.diagram.labels = ["不一致", "另一个"]
    assert len(pipeline.validate_communication(draft)) >= 3


def test_more_than_eight_scenes_rejected():
    draft = pipeline.mock_draft(data()).model_dump()
    draft["scenes"] *= 2
    with pytest.raises(ValidationError): StudioDraft.model_validate(draft)


def test_latin_words_are_not_broken_and_text_is_lossless():
    value = "科普文本confabulation不应该把英文单词随意拆开。"
    wrapped = wrap(value, 12)
    assert "".join(wrapped) == value
    assert any("confabulation" in line for line in wrapped)


def test_explicit_quote_omission_keeps_verbatim_order():
    source = "第一段原文包含足够长的明确事实说明，随后还有一段过渡内容，最后一段也包含足够长的条件限定。"
    assert pipeline.quote_is_locatable("第一段原文包含足够长的明确事实说明[…]最后一段也包含足够长的条件限定", source)
    assert not pipeline.quote_is_locatable("第一段原文包含足够长的明确事实说明，最后一段也包含足够长的条件限定", source)
    assert not pipeline.quote_is_locatable("最后一段也包含足够长的条件限定[…]第一段原文包含足够长的明确事实说明", source)
    assert not pipeline.quote_is_locatable("短片段[…]最后一段也包含足够长的条件限定", source)


def test_public_renderer_uses_copy_not_academic_quotes_and_escapes():
    p = data()
    draft = pipeline.mock_draft(p)
    draft.claims[0].text = "密密麻麻的学术术语confabulation不能出现在公众海报的正文里"
    draft.public_poster.cards[0].body = "<script>危险字符串不会成为可执行的代码</script>"
    version = {"mode": "mock", "version": 1}
    svg = render({"input": p.model_dump()}, version, draft)
    ET.fromstring(svg)
    assert "confabulation" not in svg
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    for node in draft.public_poster.nodes:
        assert node.detail in "".join(ET.fromstring(svg).itertext())


def test_wrapped_title_keeps_clear_space_before_takeaway():
    draft = pipeline.mock_draft(data())
    draft.title = "这是一个需要跨越两行来显示的公众科普海报标题"
    root = ET.fromstring(render({"input": data().model_dump()}, {"mode": "mock", "version": 1}, draft))
    elements = list(root.iter("{http://www.w3.org/2000/svg}text"))
    title_y = max(float(t.attrib["y"]) for t in elements if t.attrib["font-size"] == "52")
    takeaway_y = next(float(t.attrib["y"]) for t in elements if t.attrib["font-size"] == "28" and t.attrib["fill"] == "#ffd782")
    assert len(wrap(draft.title, 20)) > 1
    assert takeaway_y - title_y >= 88


@pytest.mark.parametrize("url", ["http://nasa.gov/page", "https://nasa.gov.evil.org/a", "https://127.0.0.1/",
    "https://nasa.gov:8000/a", "https://user:password@nasa.gov/", "https://nasa.gov/?token=secret", "file:///C:/data"])
def test_research_rejects_unapproved_urls(url):
    with pytest.raises(ValueError): research.safe_public_url(url)


def test_research_allows_real_subdomains_and_removes_fragment():
    assert research.safe_public_url("https://science.nasa.gov/moon/#phase") == "https://science.nasa.gov/moon/"


def test_dns_rejects_private_addresses():
    async def execute():
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]):
            with pytest.raises(ValueError): await research.public_dns("science.nasa.gov")
    asyncio.run(execute())


def test_html_extraction_drops_scripts_and_navigation():
    parser = research.PageText()
    parser.feed('<nav>navigation text should not become scientific evidence</nav><script>alert("private")</script>'
                '<article><p>A complete explanatory science paragraph remains in the extracted document.</p></article>')
    assert "navigation" not in parser.text()
    assert "private" not in parser.text()
    assert "explanatory" in parser.text()


def test_research_uses_only_fetched_exact_quotes_not_model_summary():
    body = "This is an original source paragraph with enough detail to support an explanation."
    class Client:
        async def studio_json(self, *args):
            return {"sources": [{"page_id": "P1", "quotes": [body], "reason": "原文说明了该现象"}], "gap": ""}, {}
    async def search(*args, **kwargs): return [{"url": "https://science.nasa.gov/test", "title": "Original source"}], {}
    async def fetch(*args): return "https://science.nasa.gov/test", body
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(Client(), "test topic", lambda label: None))
    assert result["sources"][0]["text"] == body
    assert result["selected"][0]["excerpt_sha256"]


def test_hallucinated_excerpt_not_accepted():
    class Client:
        async def studio_json(self, *args):
            return {"sources": [{"page_id": "P1", "quotes": ["This fabricated sentence must not become scientific evidence."], "reason": "与问题有关的解释"}], "gap": ""}, {}
    async def search(*args, **kwargs): return [{"url": "https://science.nasa.gov/test", "title": "Original source"}], {}
    async def fetch(*args): return "https://science.nasa.gov/test", "This is the actual page, and it says something different from the invented quotation."
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(Client(), "test topic", lambda label: None))
    assert result["sources"] == []
    assert result["gap"]


def test_empty_search_does_not_use_model_knowledge_or_select_sources():
    async def search(*args, **kwargs): return [], {}
    class Client:
        async def studio_json(self, *args): raise AssertionError("must not call selection")
    with patch.object(research, "search", side_effect=search):
        result = asyncio.run(research.research(Client(), "no match", lambda label: None))
    assert result["sources"] == []


def test_automatic_research_snapshot_is_immutable_and_project_local():
    p = store.create_project(ProjectInput(topic="问题自动检索", auto_sources=True))
    other = store.create_project(data())
    snapshot = {"sources": [s.model_dump() for s in data().sources]}
    store.save_research(p["id"], snapshot)
    assert store.get_project(p["id"])["input"]["sources"] == []
    assert store.get_project(p["id"])["research"] == snapshot
    assert store.get_project(other["id"])["research"] is None
    with pytest.raises(Exception): store.save_research(p["id"], snapshot)


def test_failed_research_stops_generation_and_is_not_automatically_rebilled():
    p = store.create_project(ProjectInput(topic="未知问题", auto_sources=True))
    async def empty(*args): return {"sources": [], "gap": "没有证据"}
    async def no_generation(*args): raise AssertionError("must not generate")
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(research, "research", side_effect=empty) as calls, patch.object(pipeline.QwenClient, "studio_json", side_effect=no_generation):
        for _ in range(2):
            request = RunInput(request_id=uuid4(), expected_version=0)
            store.reserve(p["id"], request)
            asyncio.run(pipeline.execute(p["id"], request))
        assert calls.call_count == 1
    result = store.get_project(p["id"])
    assert not result["versions"]
    assert all(r["state"] == "blocked" for r in result["runs"])


def test_vpn_fake_ip_is_opt_in_and_does_not_allow_localhost(monkeypatch):
    async def check(address):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(None, None, None, None, (address, 443))]):
            await research.public_dns("science.nasa.gov")
    monkeypatch.setenv("RESEARCH_ALLOW_VPN_FAKE_IP", "false")
    with pytest.raises(ValueError): asyncio.run(check("198.18.0.57"))
    monkeypatch.setenv("RESEARCH_ALLOW_VPN_FAKE_IP", "true")
    asyncio.run(check("198.18.0.57"))
    for address in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "198.19.0.1"]:
        with pytest.raises(ValueError): asyncio.run(check(address))


def test_studio_model_cannot_bypass_competition_model_policy():
    from app.services.model_policy import validate_model_policy
    with pytest.raises(RuntimeError): validate_model_policy(replace(settings, qwen_studio_model="gpt-4"))


def test_unsupported_dates_comparisons_and_cognitive_claims_are_blocked():
    draft = pipeline.mock_draft(data())
    draft.public_poster.cards[0].body = "它比反复阅读更好，AI没有意识，这是2025年的结论。"
    risks = pipeline.validate_communication(draft, data())
    assert any(f["severity"] == "blocker" and "年份" in f["message"] and "比较" in f["message"] and "意识" in f["message"] for f in risks)


def test_one_schema_repair_is_logged_and_rechecked():
    p = store.create_project(data())
    good = pipeline.mock_draft(data()).model_dump()
    bad = dict(good, unexpected_field="invalid")
    replies = [bad, good, {"findings": [], "revised": None}, {"findings": [], "revised": None}]
    async def model(*args): return replies.pop(0), {"purpose": args[-1]}
    request = RunInput(request_id=uuid4(), expected_version=0)
    store.reserve(p["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(p["id"], request))
    result = store.get_project(p["id"])
    assert result["runs"][-1]["state"] == "succeeded"
    assert result["versions"][0]["calls"][-1]["purpose"] == "studio_generate_schema_repair"
    assert not replies


def test_rebuild_preserves_old_version_and_records_changes():
    p = store.create_project(data())
    old = pipeline.mock_draft(data()).model_dump()
    store.append_version(p["id"], {"mode": "bailian", "draft": old})
    new = json.loads(json.dumps(old))
    new["title"] = "从证据重新讲起"
    replies = [new, {"findings": [], "revised": None}, {"findings": [], "revised": None}]
    async def model(*args): return replies.pop(0), {"purpose": args[-1]}
    request = RunInput(request_id=uuid4(), expected_version=1, rebuild=True)
    store.reserve(p["id"], request)
    with patch.object(pipeline, "settings", replace(settings, mock_ai=False)), patch.object(pipeline.QwenClient, "studio_json", side_effect=model):
        asyncio.run(pipeline.execute(p["id"], request))
    result = store.get_project(p["id"])
    assert result["versions"][0]["draft"] == old
    assert result["versions"][1]["draft"] == new
    assert result["versions"][1]["changes"][0]["field"] == "title"
    assert result["runs"][-1]["state"] == "succeeded"


def test_display_consistency_is_mechanical_and_idempotent():
    draft = pipeline.mock_draft(data())
    saved = [n.model_dump() for n in draft.public_poster.nodes]
    draft.diagram.labels = ["旧标签", "未同步"]
    changes = pipeline.synchronize_display_labels(draft)
    assert changes[0]["actor"] == "program_display_consistency"
    assert changes[0]["before"] == ["旧标签", "未同步"]
    assert [n.model_dump() for n in draft.public_poster.nodes] == saved
    assert draft.diagram.labels == [n.label for n in draft.public_poster.nodes]
    assert pipeline.synchronize_display_labels(draft) == []
