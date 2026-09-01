import asyncio
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import wave

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import studio_store as store, studio_research as research, studio_pipeline as pipeline
from app.studio_models import ProjectInput, Source, MediaInput, RunInput


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIENCE_POSTER_DATA_DIR", str(tmp_path))


def project():
    data = ProjectInput(topic="基础概念", sources=[Source(source_id="S1", title="测试原文", text="这是一份用来测试数据校验的原始资料，说明系统如何保留原文而不是编造引用。")])
    p = store.create_project(data)
    store.append_version(p["id"], {"mode": "bailian", "review_status": "ai_checked_human_pending", "draft": pipeline.mock_draft(data).model_dump()})
    return store.get_project(p["id"])


def test_api_glossary_and_technical_hosts_are_allowed_not_lookalikes():
    assert research.safe_public_url(research.GLOSSARY["API"])
    assert "developer.mozilla.org" in research.PROFILES["technology"]
    for bad in ["https://developer.mozilla.org.evil.test/a", "https://evil.test/developer.mozilla.org", "https://learn.microsoft.com/?key=private"]:
        with pytest.raises(ValueError): research.safe_public_url(bad)


def test_article_preferred_to_long_site_chrome():
    parser = research.PageText()
    parser.feed("<div>" + "unrelated site content " * 500 + "</div><main><p>" + "Actual relevant body content. " * 20 + "</p></main>")
    assert "Actual relevant" in parser.text()
    assert "unrelated" not in parser.text()


def test_unverified_answer_survives_failed_search_without_becoming_source():
    class Client:
        async def studio_json(self, *args):
            assert args[-1] == "studio_question_orientation"
            return {"domain": "technology", "answer": "这是一段模型自己的初步解释，仅供帮助理解，不是经过外部原文核实的正式结论。", "queries": ["unknown one", "unknown two"]}, {}
    async def search(*args, **kwargs): return [], {}
    with patch.object(research, "search", side_effect=search):
        result = asyncio.run(research.research(Client(), "未知基础问题", lambda _: None))
    assert result["explanation"]["status"] == "model_background_unverified"
    assert result["sources"] == [] and result["gap"]
    assert len(result["calls"]) == 5  # orientation + four bounded retrieval attempts


def test_technology_catalog_is_fetched_when_search_plugin_is_unavailable():
    class Client:
        async def studio_json(self, *args):
            if args[-1] == "studio_question_orientation":
                return {"domain":"technology","answer":"API 是软件之间按约定请求功能或数据的接口，仍须读取官方原文后再作为作品依据。",
                        "queries":["API 应用程序编程接口","what is API official documentation"],"preferred_sites":["developer.mozilla.org"]}, {}
            return {"sources":[{"page_id":"P1","passage_ids":["P1-L001"],"reason":"官方术语页解释API"},
                               {"page_id":"P2","passage_ids":["P2-L001"],"reason":"官方概念指南解释API作用"}],"gap":""}, {}
    async def unavailable(*args, **kwargs):
        raise research.httpx.ConnectError("search temporarily unavailable")
    visited=[]
    async def fetch(url):
        visited.append(url)
        return url, "API is a documented interface that lets software components communicate through agreed requests and responses. " * 3
    with patch.object(research,"search",side_effect=unavailable), patch.object(research,"fetch_page",side_effect=fetch):
        result=asyncio.run(research.research(Client(),"API是什么？",lambda _:None))
    assert visited == [research.GLOSSARY["API"], research.CONCEPT_GUIDES["API"]]
    assert len(result["sources"]) == 2
    assert result["events"][0]["state"] == "搜索服务未完成"


def test_source_selection_over_limit_keeps_verified_prefix_instead_of_dropping_source():
    class Client:
        async def studio_json(self,*args):
            if args[-1]=="studio_question_orientation":
                return {"domain":"science","answer":"这是模型生成的初步解释，只帮助理解问题方向，仍需从公开原文逐字核验后才能作为证据进入最终科普作品。",
                        "queries":["test science concept","test science official"],"candidate_urls":["https://science.nasa.gov/test"]},{}
            return {"sources":[{"page_id":"P1","passage_ids":["P1-L001","P1-L002","P1-L003"],"reason":"三个段落共同解释概念"}],"gap":""},{}
    async def empty(*args,**kwargs): return [],{}
    paragraphs=[("A"*390)+".",("B"*390)+".",("C"*390)+"."]
    async def fetch(url): return url,"\n".join(paragraphs)
    with patch.object(research,"search",side_effect=empty),patch.object(research,"fetch_page",side_effect=fetch):
        result=asyncio.run(research.research(Client(),"测试科学概念",lambda _:None))
    assert len(result["sources"])==1
    assert result["selected"][0]["passage_ids"]==["P1-L001","P1-L002"]
    assert len(result["sources"][0]["text"])<=900
    assert any("自动裁剪" in event["state"] for event in result["events"])


def test_filtered_results_retry_and_log_without_saving_secret_urls():
    class Client:
        async def studio_json(self, *args):
            return {"domain": "science", "answer": "初步解释不等于科学证据；来源搜索失败仍会保留明确标识的概念回答供用户阅读。", "queries": ["q1", "q2"]}, {}
    seen = []
    async def search(*args, **kwargs):
        seen.append(kwargs["restricted"])
        return [{"url": "https://bad.example/?secret=abc"}], {}
    with patch.object(research, "search", side_effect=search):
        result = asyncio.run(research.research(Client(), "unknown", lambda _: None))
    assert seen == [True, False, False, False]
    assert result["events"] and "secret" not in str(result)


def test_media_idempotency_and_script_lock():
    p = project(); r = MediaInput(request_id=uuid4(), expected_version=1)
    assert store.reserve_media(p["id"], r)
    assert not store.reserve_media(p["id"], r)
    with pytest.raises(ValueError): store.reserve(p["id"], RunInput(request_id=uuid4(), expected_version=1))
    with pytest.raises(ValueError): store.reserve_media(p["id"], MediaInput(request_id=uuid4(), expected_version=1))
    with pytest.raises(ValueError): store.reserve_media(p["id"], MediaInput(request_id=r.request_id, expected_version=2))
    job = store.get_project(p["id"])["media"][0]
    job["state"] = "succeeded"; store.save_media(p["id"], job)
    with pytest.raises(ValueError): store.reserve_media(p["id"], MediaInput(request_id=uuid4(), expected_version=1))


def test_media_recovery_preserves_scenes_and_marks_interrupted():
    p = project(); request = MediaInput(request_id=uuid4(), expected_version=1)
    store.reserve_media(p["id"], request)
    job = store.get_project(p["id"])["media"][0]
    job["scenes"] = [{"accepted": "sample.png"}]
    store.save_media(p["id"], job); store.recover_interrupted_runs()
    result = store.get_project(p["id"])["media"][0]
    assert result["state"] == "failed" and result["scenes"] == job["scenes"]


def test_media_refuses_blocked_or_stale_scripts():
    p = project()
    with pytest.raises(ValueError): store.reserve_media(p["id"], MediaInput(request_id=uuid4(), expected_version=2))
    store.append_version(p["id"], dict(p["versions"][0], review_status="blocked"))
    with pytest.raises(ValueError): store.reserve_media(p["id"], MediaInput(request_id=uuid4(), expected_version=2))


def test_media_route_never_serves_unlisted_files():
    p = project(); request = MediaInput(request_id=uuid4(), expected_version=1)
    store.reserve_media(p["id"], request)
    with TestClient(app) as client:
        assert client.get(f"/api/studio/projects/{p['id']}/media/{request.request_id}/.env").status_code == 404


def test_two_rejected_images_stop_before_voice_and_preserve_corrections(tmp_path, monkeypatch):
    pytest.importorskip("PIL"); pytest.importorskip("imageio_ffmpeg")
    from app.services import studio_media as media
    from dataclasses import replace
    from types import SimpleNamespace
    p = project(); r = MediaInput(request_id=uuid4(), expected_version=1, renderer="illustrated")
    store.reserve_media(p["id"], r)
    monkeypatch.setattr(media, "settings", replace(media.settings, mock_ai=False, dashscope_api_key="test-not-a-real-key"))
    monkeypatch.setattr(media, "directory", lambda *args: tmp_path / "media")
    monkeypatch.setattr(media, "guard_text_budget", lambda *args: None)
    async def planned(draft): return {s.scene_id: "A plain text-free cartoon for this scene." for s in draft.scenes}, {}
    monkeypatch.setattr(media, "plan_illustrations", planned)
    async def generated(self, spec, folder, **kwargs):
        return SimpleNamespace(asset=SimpleNamespace(file_path=str(folder / f"candidate-{spec.version}.png"), model="qwen-image-test"), request_id="test-image")
    async def inspected(*args): return {"status": "revise", "issues": ["测试：画面不符"], "repair": "只改画面中的错误关系"}
    async def no_voice(*args): raise AssertionError("Rejected images must never reach voice synthesis")
    monkeypatch.setattr(media.QwenImageClient, "generate", generated)
    monkeypatch.setattr(media, "inspect_image", inspected)
    monkeypatch.setattr(media.QwenTtsClient, "generate", no_voice)
    asyncio.run(media.execute_media(p["id"], r))
    job = store.get_project(p["id"])["media"][0]
    assert job["state"] == "blocked"
    assert len(job["scenes"][0]["candidates"]) == 2
    assert job["scenes"][0]["candidates"][1]["correction"] == "只改画面中的错误关系"
    assert job["scenes"][0]["accepted"] == ""


def test_unbacked_security_guarantee_blocked():
    p = project(); from app.studio_models import StudioDraft
    draft = StudioDraft.model_validate(p["versions"][0]["draft"])
    draft.takeaway = "只要使用一个接口就可以保证安全协作。"
    assert any(f["severity"] == "blocker" and "安全" in f["message"] for f in pipeline.validate_communication(draft, ProjectInput.model_validate(p["input"])))
    draft.takeaway = "有接口并不代表能够保证安全，仍需看具体设计。"
    assert not any("安全/权限" in f["message"] for f in pipeline.validate_communication(draft, ProjectInput.model_validate(p["input"])))


def test_video_composition_uses_actual_audio_and_keeps_all_words(tmp_path):
    pytest.importorskip("PIL"); pytest.importorskip("imageio_ffmpeg")
    from PIL import Image
    from app.services.studio_video import compose, find_font
    from app.studio_models import StudioDraft
    try: find_font()
    except RuntimeError: pytest.skip("No Chinese font in test environment")
    p = project(); draft = StudioDraft.model_validate(p["versions"][0]["draft"])
    image = tmp_path / "illustration.png"; Image.new("RGB", (1024, 576), "#fff099").save(image)
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(b"\0\0" * 6000)
    result = compose(draft, [image] * 6, [voice] * 6, tmp_path)
    assert result["duration_seconds"] == 1.5
    assert (tmp_path / "preview.mp4").stat().st_size > 1000
    assert (tmp_path / "poster.png").stat().st_size > 1000
    assert "00:00:01,500" in (tmp_path / "subtitles.srt").read_text(encoding="utf-8")


def test_model_suggested_url_is_only_evidence_after_fetch_and_quote_validation():
    url = "https://science.nasa.gov/moon/moon-phases/"
    quote = "The Moon does not make its own light. Moonlight is reflected sunlight."
    class Client:
        async def studio_json(self, *args):
            if args[-1] == "studio_question_orientation":
                return {"domain": "science", "answer": "这只是模型的初步解释，并非已查证的事实，只有实际读取并校验原文后才可作为作品的依据。",
                        "queries": ["月相", "moon phases"], "preferred_sites": ["nasa.gov", "evil.test"],
                        "candidate_urls": [url, "https://bad.test/?secret=abc"]}, {}
            return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"], "reason": "原文介绍月球反射阳光"}]}, {}
    visited = []
    async def search(*args, **kwargs):
        assert kwargs["sites"] == ["nasa.gov"]
        return [], {}
    async def fetch(u): visited.append(u); return u, quote * 4
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(Client(), "月相为什么变化", lambda _: None))
    assert visited == [url]
    assert result["sources"][0]["text"] == quote * 4
    assert result["events"][0]["discovery"] == "model_candidate_verified_by_fetch"
    assert "secret" not in str(result) and "candidate_urls" not in result["explanation"]


def test_selector_error_keeps_model_answer_but_never_claims_verified():
    class Client:
        async def studio_json(self, *args):
            if args[-1] == "studio_question_orientation":
                return {"domain": "science", "answer": "这只是模型的初步解释，并非已查证的事实，只有实际读取并校验原文后才可作为作品的依据。",
                        "queries": ["q1", "q2"]}, {}
            raise ValueError("bad selection JSON")
    async def search(*args, **kwargs): return [{"url": "https://nasa.gov/article"}], {}
    async def fetch(u): return u, "A sufficiently long source paragraph. " * 20
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(Client(), "science", lambda _: None))
    assert not result["sources"] and result["explanation"]["status"] == "model_background_unverified"
    assert "摘录校验未完成" in result["gap"]


def test_media_retry_reuses_completed_assets_without_paid_calls(tmp_path, monkeypatch):
    pytest.importorskip("PIL"); pytest.importorskip("imageio_ffmpeg")
    from app.services import studio_media as media, studio_video as video
    from dataclasses import replace
    p = project(); old_request = MediaInput(request_id=uuid4(), expected_version=1, renderer="illustrated")
    store.reserve_media(p["id"], old_request)
    old = store.get_project(p["id"])["media"][0]
    old_dir = tmp_path / str(old_request.request_id); old_dir.mkdir()
    (old_dir / "image.png").write_bytes(b"image fixture")
    (old_dir / "voice.wav").write_bytes(b"voice fixture")
    old.update(state="failed", files=["image.png", "voice.wav"], scenes=[
        {"scene_id": s["scene_id"], "candidates": [{"file": "image.png", "attempt": 1, "review": {"status": "pass"}}],
         "accepted": "image.png", "voice": {"file": "voice.wav"}} for s in p["versions"][0]["draft"]["scenes"]])
    store.save_media(p["id"], old)
    r = MediaInput(request_id=uuid4(), expected_version=1, renderer="illustrated"); store.reserve_media(p["id"], r)
    monkeypatch.setattr(media, "directory", lambda _p, job: tmp_path / job)
    monkeypatch.setattr(media, "settings", replace(media.settings, mock_ai=False, dashscope_api_key="test-not-real"))
    monkeypatch.setattr(video, "find_font", lambda: "test-font")
    def compose(draft, images, audio, folder):
        assert len(images) == len(draft.scenes) == len(audio)
        assert all(path.read_bytes() == b"image fixture" for path in images)
        return {"video": "preview.mp4"}
    monkeypatch.setattr(video, "compose", compose)
    async def forbidden(*args, **kwargs): raise AssertionError("Completed media must not incur new calls")
    monkeypatch.setattr(media.QwenImageClient, "generate", forbidden)
    monkeypatch.setattr(media.QwenTtsClient, "generate", forbidden)
    monkeypatch.setattr(media, "inspect_image", forbidden)
    asyncio.run(media.execute_media(p["id"], r))
    result = store.get_project(p["id"])
    assert result["media"][-1]["state"] == "succeeded"
    assert result["media"][-1]["resumed_from"] == str(old_request.request_id)
    assert result["media"][0]["state"] == "failed"


@pytest.mark.parametrize("make_video,mock,state,expected", [(True,False,"succeeded",1), (False,False,"succeeded",0), (True,True,"succeeded",0), (True,False,"blocked",0), (True,False,"failed",0)])
def test_automatic_video_only_after_successful_real_review(monkeypatch, make_video, mock, state, expected):
    from app import studio_routes as routes
    from app.services import studio_media as media
    from dataclasses import replace
    p = project(); request = RunInput(request_id=uuid4(), expected_version=1, make_video=make_video)
    store.reserve(p["id"], request)
    async def reviewed(pid, r): store.stage(r.request_id, "test review", state)
    calls = []
    async def rendered(pid, r): calls.append(r)
    monkeypatch.setattr(routes, "execute", reviewed)
    monkeypatch.setattr(routes, "settings", replace(routes.settings, mock_ai=mock))
    monkeypatch.setattr(media, "execute_media", rendered)
    asyncio.run(routes.execute_with_video(p["id"], request))
    assert len(calls) == expected
    if expected:
        assert calls[0].renderer == "cartoon" and calls[0].expected_version == 1
        asyncio.run(routes.execute_with_video(p["id"], request))
        assert len(calls) == 1  # Same run cannot create a second paid media request.


def test_cartoon_objects_really_move_and_reject_unsupported_icons():
    from app.services.studio_cartoon import CartoonScene, frame
    from PIL import ImageChops
    plan = {"scene_id":"S1", "relationship":"exchange", "caption":"两个软件按照约定交换请求与结果。", "actors":[
        {"icon":"phone","label":"手机应用","explanation":"发出查天气请求"},
        {"icon":"server","label":"天气服务","explanation":"按约定返回天气资料"}]}
    assert ImageChops.difference(frame(plan,.1,"软件如何合作"), frame(plan,.8,"软件如何合作")).getbbox()
    plan["actors"][0]["icon"]="unknown-icon"
    with pytest.raises(ValueError): CartoonScene.model_validate(plan)


def test_cartoon_entrance_never_collides_with_labels(monkeypatch):
    from app.services import studio_cartoon as cartoon
    bottoms = []
    def capture(draw, icon, x, y, t, radius=62): bottoms.append(y+94)
    monkeypatch.setattr(cartoon,"draw_actor",capture)
    plan = {"scene_id":"S1","relationship":"reveal","caption":"角色入场不能挡住下面的解释文字。","actors":[
        {"icon":"sun","label":"角色","explanation":"保证所有文字清楚可读"} for _ in range(4)]}
    for phase in (0,.1,.2,.4,.6,.8,1): cartoon.frame(plan,phase,"入场布局回归")
    assert max(bottoms) < 413  # Label baseline starts below the largest actor extent.


def test_unknown_cartoon_icon_is_mechanically_mapped_without_changing_meaning():
    from app.services.studio_cartoon import normalize_actor_icons, CartoonPlan
    raw={"scenes":[{"scene_id":f"V{i}","relationship":"reveal","caption":"模型给出流畅回答，但内容仍需要核查。","actors":[
        {"icon":"brain","label":"AI模型","explanation":"根据输入生成回答"},{"icon":"magnifier","label":"核查者","explanation":"回到资料检查事实"}]} for i in range(1,4)]}
    before={k:v for k,v in raw["scenes"][0].items() if k != "actors"}
    changes=normalize_actor_icons(raw)
    assert [a["icon"] for a in raw["scenes"][0]["actors"]] == ["robot","book"]
    assert {k:v for k,v in raw["scenes"][0].items() if k != "actors"} == before
    assert len(changes)==6
    assert CartoonPlan.model_validate(raw)


def test_cartoon_composition_has_video_and_subtitles_but_no_default_poster(tmp_path, monkeypatch):
    from app.services import studio_video as video
    from app.studio_models import StudioDraft
    from PIL import Image
    draft = StudioDraft.model_validate(project()["versions"][0]["draft"])
    image = tmp_path / "frame.png"; Image.new("RGB",(1280,720),"#08252f").save(image)
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice),"wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(b"\0\0"*6000)
    # Qwen TTS can return a valid PCM payload with an oversized WAV data-length header.
    malformed=bytearray(voice.read_bytes());malformed[40:44]=(0x7ffffffe).to_bytes(4,"little");voice.write_bytes(malformed)
    real_combine = video.combine_audio
    def fast_combine(paths, target, pad):
        assert pad == 68
        return real_combine(paths,target,0)
    monkeypatch.setattr(video,"combine_audio",fast_combine)
    plans=[{"scene_id":s.scene_id,"relationship":"reveal","caption":"按已有资料展示主要对象及关系。","actors":[
        {"icon":"book","label":"资料","explanation":"先查看已有的证据"},
        {"icon":"person","label":"公众","explanation":"再解释知识的含义"}]} for s in draft.scenes]
    result=video.compose(draft,[image]*6,[voice]*6,tmp_path,cartoon_plans=plans)
    assert result["fps"] == 20 and result["duration_seconds"] == 1.5
    assert "poster" not in result and not (tmp_path/"poster.png").exists()
    assert (tmp_path/"preview.mp4").stat().st_size > 1000
    subtitles=(tmp_path/"subtitles.srt").read_text(encoding="utf-8")
    lines=[line for line in subtitles.splitlines() if "-->" in line]
    assert lines and all(not line.startswith("-") for line in lines)
    assert lines[-1].endswith("00:00:01,500")


def test_video_captions_keep_complete_sentences_and_merge_short_tail():
    from app.services.studio_video import complete_sentence_captions
    text="AI像人说话，是因为学了大量人类语言。但这只是常见组合方式，并不保证内容正确。"
    assert complete_sentence_captions(text) == [
        "AI像人说话，是因为学了大量人类语言。",
        "但这只是常见组合方式，并不保证内容正确。",
    ]
    assert complete_sentence_captions("第一句话已经完整。补充说明") == ["第一句话已经完整。补充说明"]


def test_bot_check_placeholder_is_rejected_not_treated_as_extracted():
    assert research.looks_like_bot_check("Checking your browser - reCAPTCHA\nChecking your browser before accessing pmc.ncbi.nlm.nih.gov ...")
    assert research.looks_like_bot_check("正在验证您的访问，请稍候。人机验证页面即将跳转。")
    assert not research.looks_like_bot_check("这是一段正常的公开科普正文。" * 60)
    assert not research.looks_like_bot_check(("captcha appears nowhere here but the page is long. " * 300)[:2400])


def test_education_backstops_use_readable_entry_pages_with_real_titles():
    urls = [entry[1] for entry in research.DOMAIN_BACKSTOPS["education"]]
    assert "pmc.ncbi.nlm.nih.gov" not in " ".join(urls)  # reCAPTCHA-gated, rejected at fetch
    assert any("ies.ed.gov" in u for u in urls)
    assert any("openstax.org" in u for u in urls)
    titles = {entry[1]: entry[2] for entry in research.DOMAIN_BACKSTOPS["education"]}
    assert "官方概念页" not in " ".join(titles.values())  # no developer-note titles in the UI
    assert titles["https://openstax.org/books/psychology-2e/pages/8-1-how-memory-functions"].startswith("OpenStax")


def test_backstop_catalog_titles_reach_fetched_pages():
    class Client:
        def __init__(self): self.seen_pages = []
        async def studio_json(self, *args):
            purpose = args[-1]
            if purpose == "studio_question_orientation":
                return {"domain": "education", "answer": "间隔复习是教育研究建议的复习方法，需要官方资料核实后再作为作品依据。",
                        "queries": ["间隔复习 记忆", "spacing study memory"], "preferred_sites": ["ies.ed.gov"]}, {}
            self.seen_pages.append(args[1].get("pages", []))
            return {"sources": [], "gap": "无可用来源"}, {}
    async def search(*args, **kwargs): return [], {}
    async def fetch(url):
        return url, "This is a sufficiently long public page body about spaced practice and memory traces. " * 30
    client = Client()
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        asyncio.run(research.research(client, "为什么重复复习要隔一段时间", lambda _: None))
    pages = client.seen_pages[-1]
    titles = [p["title"] for p in pages]
    assert any("IES 实践指南" in t for t in titles)


def test_mechanism_gap_triggers_second_pass_selection_and_clears_gap():
    class Client:
        def __init__(self): self.purposes = []
        async def studio_json(self, *args):
            purpose = args[-1]
            self.purposes.append(purpose)
            if purpose == "studio_question_orientation":
                return {"domain": "education", "answer": "间隔复习是教育研究建议的复习方法，需要官方资料核实后再作为作品依据。",
                        "queries": ["间隔复习 记忆", "spacing study memory"], "preferred_sites": ["ies.ed.gov"]}, {}
            if purpose == "studio_source_selection":
                return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"], "reason": "官方实践指南给出间隔复习建议"}],
                        "gap": "未解释间隔复习为何有效的认知机制。"}, {}
            return {"sources": [{"page_id": "P2", "passage_ids": ["P2-L001"], "reason": "教材解释记忆如何进入长期记忆"}], "gap": ""}, {}
    async def search(*args, **kwargs): return [], {}
    async def fetch(url):
        if "ies.ed.gov" in url:
            body = "Space learning over time. Arrange to review key elements of course content after a delay of several weeks to several months after initial presentation. " * 4
        else:
            body = "Active rehearsal is a way of attending to information to move it from short-term to long-term memory. Storage keeps the encoded information available for later use. " * 4
        return url, body
    client = Client()
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(client, "为什么重复复习要隔一段时间", lambda _: None))
    assert "studio_source_selection_second_pass" in client.purposes
    assert len(result["sources"]) == 2
    assert any("OpenStax" in s["title"] for s in result["sources"])
    assert result["gap"] == ""


def test_second_pass_without_mechanism_passages_preserves_gap():
    class Client:
        async def studio_json(self, *args):
            purpose = args[-1]
            if purpose == "studio_question_orientation":
                return {"domain": "education", "answer": "间隔复习是教育研究建议的复习方法，需要官方资料核实后再作为作品依据。",
                        "queries": ["间隔复习 记忆", "spacing study memory"], "preferred_sites": ["ies.ed.gov"]}, {}
            if purpose == "studio_source_selection":
                return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"], "reason": "官方实践指南给出间隔复习建议"}],
                        "gap": "未解释间隔复习为何有效的认知机制。"}, {}
            return {"sources": [], "gap": "这些页面同样没有机制解释。"}, {}
    async def search(*args, **kwargs): return [], {}
    async def fetch(url):
        body = "This page only repeats practical advice without explaining underlying mechanisms. " * 6
        return url, body
    client = Client()
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(client, "为什么重复复习要隔一段时间", lambda _: None))
    assert len(result["sources"]) == 1
    assert result["gap"].startswith("未解释间隔复习")


def test_empty_first_selection_gets_one_bounded_partial_support_retry():
    class Client:
        def __init__(self): self.purposes = []
        async def studio_json(self, *args):
            purpose = args[-1]
            self.purposes.append(purpose)
            if purpose == "studio_question_orientation":
                return {"domain": "general", "answer": "水看起来是什么颜色，既与水本身吸收和散射光有关，也可能受到水中物质和周围环境影响，需要可靠资料核实。",
                        "queries": ["水 颜色 原因 科普", "why water has different colors science explainer"]}, {}
            if purpose == "studio_source_selection":
                return {"sources": [], "gap": "第一轮没有完整机制资料。"}, {}
            if purpose == "studio_source_selection_recovery":
                return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"],
                                      "reason": "原文直接说明水色受水中物质影响"}],
                        "gap": "该来源只支持可观察因素，未覆盖全部光学机制。"}, {}
            assert purpose == "studio_source_selection_second_pass"
            return {"sources": [], "gap": "其余页面没有补充光学机制。"}, {}
    async def search(*args, **kwargs):
        return [{"url": "https://www.usgs.gov/example-water-color", "title": "USGS water color"}], {}
    async def fetch(url):
        return url, "Water color can vary when dissolved material and suspended particles change how light travels through the water. " * 4
    client = Client()
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(client, "不同地方水的颜色为什么不一样", lambda _: None))
    assert "studio_source_selection_recovery" in client.purposes
    assert len(result["sources"]) == 1
    assert result["sources"][0]["text"].startswith("Water color can vary")


def test_general_water_question_has_verified_readable_entry_points_when_search_is_empty():
    class Client:
        async def studio_json(self, *args):
            purpose = args[-1]
            if purpose == "studio_question_orientation":
                return {"domain": "science", "answer": "不同水体会因为水本身和其中物质与光相互作用不同而呈现不同颜色，需要读取权威原文核实。",
                        "queries": ["水体颜色 原因", "water color causes science"]}, {}
            return {"sources": [{"page_id": "P1", "passage_ids": ["P1-L001"],
                                  "reason": "权威科普页面直接解释水体颜色"}], "gap": ""}, {}
    async def search(*args, **kwargs): return [], {}
    visited = []
    async def fetch(url):
        visited.append(url)
        return url, "Water color varies because dissolved substances, algae, and suspended sediment change how light behaves in natural water. " * 4
    with patch.object(research, "search", side_effect=search), patch.object(research, "fetch_page", side_effect=fetch):
        result = asyncio.run(research.research(Client(), "不同地方水的颜色为什么不一样", lambda _: None))
    assert "https://oceanservice.noaa.gov/facts/oceanblue.html" in visited
    assert "https://www.sciencelearn.org.nz/resources/3134-remote-sensing-and-water-quality" in visited
    assert result["sources"] and result["sources"][0]["url"].startswith("https://oceanservice.noaa.gov/")
