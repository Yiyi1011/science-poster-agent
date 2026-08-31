from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models import FactCard, PosterPlan
from app.services.bailian_app_client import parse_retrieval_response, workspace_origin
from app.services.usage_ledger import estimate_text_cost
from app.services.pipeline import _retrieval_source_text
from app.models import KnowledgeAnswer, KnowledgeReference
from app.services.svg_renderer import render_poster_svg
from app.models import ReviewIssue, RevisionRequest
from app.services.visual_workflow import (
    build_revision_plan,
    build_video_storyboard,
    build_visual_asset_bundle,
    persist_version,
)
from app.services.qwen_image_client import parse_image_response, validate_result_url
from app.services.usage_ledger import record_image_usage


client = TestClient(app)


def test_health_does_not_expose_secrets() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()


def test_mock_plan_requires_sources() -> None:
    with patch("app.services.pipeline.settings", replace(settings, mock_ai=True)):
        response = client.post(
            "/api/posters/plan",
            json={"topic": "测试主题", "audience": "普通公众", "source_text": ""},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_sources"
    assert payload["fact_cards"][0]["evidence_status"] == "missing"


def test_fact_card_normalizes_empty_model_evidence() -> None:
    card = FactCard.model_validate(
        {
            "claim_id": "C-001",
            "claim": "证据不足时不形成正式科学结论。",
            "evidence_status": "missing",
            "evidence": "",
            "caveat": "仅验证模型返回兼容性。",
        }
    )
    assert card.evidence == []


def test_fact_card_normalizes_qwen_confirmed_and_string_document_id() -> None:
    card = FactCard.model_validate(
        {
            "claim_id": "C-002",
            "claim": "测试事实",
            "evidence_status": "confirmed",
            "evidence": ["file_safe_document_id"],
        }
    )
    assert card.evidence_status == "supported"
    assert card.evidence[0].source_id == "file_safe_document_id"


def test_estimate_text_cost() -> None:
    assert estimate_text_cost(1_000_000, 500_000, 0.8, 2.0) == 1.8


def test_retrieval_url_uses_same_workspace_host() -> None:
    configured = replace(
        settings,
        dashscope_base_url=(
            "https://llm-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
        dashscope_app_base_url="",
    )
    assert workspace_origin(configured) == (
        "https://llm-example.cn-beijing.maas.aliyuncs.com"
    )


def test_retrieval_threshold_uses_node_score() -> None:
    body = {
        "request_id": "safe-test-id",
        "data": {
            "nodes": [
                {
                    "score": 0.878,
                    "text": "测试切片",
                    "metadata": {"doc_name": "边界文档", "doc_id": "doc-1"},
                }
            ]
        },
    }
    result = parse_retrieval_response(body, threshold=0.50)
    assert result.status == "supported"
    assert result.max_retrieval_score == 0.878
    assert result.references[0].doc_name == "边界文档"


def test_retrieval_below_threshold_refuses() -> None:
    body = {
        "request_id": "safe-test-id",
        "data": {"nodes": [{"score": 0.385, "text": "相似但不支持结论", "metadata": {}}]},
    }
    result = parse_retrieval_response(body, threshold=0.50)
    assert result.status == "insufficient_evidence"
    assert "证据不足" in result.answer


def test_only_threshold_passing_chunks_feed_generation() -> None:
    retrieval = KnowledgeAnswer(
        status="supported",
        answer="ready",
        references=[
            KnowledgeReference(
                index_id="1",
                doc_id="doc-pass",
                doc_name="通过文档",
                text="应进入生成模型",
                score=0.81,
            ),
            KnowledgeReference(
                index_id="2",
                doc_id="doc-fail",
                doc_name="低分文档",
                text="不得进入生成模型",
                score=0.31,
            ),
        ],
        max_retrieval_score=0.81,
        threshold=0.50,
        gate_reason="retrieval_score_passed",
    )
    source_text = _retrieval_source_text(retrieval)
    assert "应进入生成模型" in source_text
    assert "不得进入生成模型" not in source_text


def test_svg_renderer_outputs_editable_vector() -> None:
    with patch("app.services.pipeline.settings", replace(settings, mock_ai=True)):
        payload = client.post(
            "/api/posters/plan",
            json={"topic": "测试主题", "source_text": "权威资料"},
        ).json()
    plan = render_poster_svg(PosterPlan.model_validate(payload))
    assert plan.startswith("<svg")
    assert "测试主题" in plan
    assert "强耀斑" not in plan
    assert "生成内容已进入人工科学审核" in plan


def test_poster_plan_normalizes_model_safety_note_list() -> None:
    plan = _mock_poster_plan().model_dump()
    plan["safety_note"] = ["边界一", "边界二"]
    assert PosterPlan.model_validate(plan).safety_note == "边界一；边界二"


def test_svg_renderer_labels_direct_source_route_without_fake_rag_score() -> None:
    plan = _mock_poster_plan().model_copy(update={"retrieval_status": "user_sources"})
    svg = render_poster_svg(plan)
    assert "权威资料直接输入" in svg
    assert "MAX SCORE 0.000" not in svg


def test_unified_server_serves_built_frontend() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<div id=\"root\"></div>" in response.text


def test_unknown_api_route_does_not_fall_back_to_frontend() -> None:
    response = client.get("/api/not-a-real-route")
    assert response.status_code == 404
    assert response.json()["detail"] == "API route not found"


def _mock_poster_plan() -> PosterPlan:
    with patch("app.services.pipeline.settings", replace(settings, mock_ai=True)):
        payload = client.post(
            "/api/posters/plan",
            json={"topic": "太阳爆发", "source_text": "权威资料"},
        ).json()
    return PosterPlan.model_validate(payload)


def test_visual_asset_bundle_links_assets_to_claims() -> None:
    bundle = build_visual_asset_bundle(_mock_poster_plan(), persist=False)
    assert bundle.assets[0].source_claim_ids == ["C-001"]
    assert "不要生成标题" in bundle.assets[0].prompt
    assert bundle.generation_budget_cny == 10


def test_fact_issue_blocks_automatic_revision() -> None:
    revision = build_revision_plan(
        RevisionRequest(
            task_id="safe-task",
            issues=[
                ReviewIssue(
                    issue_id="issue-1",
                    target_id="asset-1",
                    category="fact",
                    severity="major",
                    description="图像与事实卡不一致",
                )
            ],
        ),
        persist=False,
    )
    assert revision.status == "blocked_by_evidence"
    assert revision.actions[0].action == "request_more_sources"


def test_layout_issue_creates_local_patch() -> None:
    revision = build_revision_plan(
        RevisionRequest(
            task_id="safe-task",
            issues=[
                ReviewIssue(
                    issue_id="issue-2",
                    target_id="poster-v1",
                    category="layout",
                    severity="minor",
                    description="来源区过密",
                )
            ],
        ),
        persist=False,
    )
    assert revision.status == "ready_for_review"
    assert revision.actions[0].action == "patch_layout"


def test_video_storyboard_uses_ai_voice_and_subtitles() -> None:
    storyboard = build_video_storyboard(_mock_poster_plan(), persist=False)
    assert storyboard.narration_mode == "ai_voice_with_subtitles"
    assert storyboard.total_duration_seconds > 0
    assert all(scene.subtitle for scene in storyboard.scenes)


def test_version_store_never_overwrites(tmp_path) -> None:
    first = persist_version("safe-task", "visual-assets", {"value": 1}, root=tmp_path)
    second = persist_version("safe-task", "visual-assets", {"value": 2}, root=tmp_path)
    assert first.endswith("v001.json")
    assert second.endswith("v002.json")


def test_parse_image_response() -> None:
    image_url, request_id, count, width, height = parse_image_response(
        {
            "request_id": "safe-request",
            "output": {"choices": [{"message": {"content": [{"image": "https://safe.oss-cn-beijing.aliyuncs.com/result.png"}]}}]},
            "usage": {"output_image_count": 1, "output_width": 768, "output_height": 1024},
        }
    )
    assert image_url.endswith("result.png")
    assert (request_id, count, width, height) == ("safe-request", 1, 768, 1024)


def test_image_result_url_blocks_non_aliyun_host() -> None:
    with __import__("pytest").raises(RuntimeError):
        validate_result_url("https://example.com/untrusted.png")


def test_official_aliyun_http_result_is_upgraded_to_https() -> None:
    from app.services.qwen_image_client import secure_aliyun_result_url

    secured = secure_aliyun_result_url(
        "http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/safe.wav"
    )
    assert secured.startswith("https://")


def test_parse_tts_response() -> None:
    from app.services.qwen_tts_client import parse_tts_response

    url, request_id = parse_tts_response(
        {
            "request_id": "safe-tts-request",
            "output": {"audio": {"url": "https://safe.oss-cn-beijing.aliyuncs.com/audio.wav"}},
        }
    )
    assert url.endswith("audio.wav")
    assert request_id == "safe-tts-request"


def test_wav_duration() -> None:
    import io
    import wave

    from app.services.qwen_tts_client import wav_duration

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 24000)
    assert wav_duration(buffer.getvalue()) == 1.0


def test_parse_vision_json_content_removes_fence() -> None:
    from app.services.qwen_vision_reviewer import parse_json_content

    result = parse_json_content('```json\n{"status":"pass"}\n```')
    assert result["status"] == "pass"
