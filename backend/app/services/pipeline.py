from __future__ import annotations

from uuid import uuid4

from app.config import settings
from app.models import FactCard, KnowledgeAnswer, PosterPlan, PosterRequest, PosterSection
from app.services.bailian_app_client import BailianKnowledgeAppClient
from app.services.qwen_client import QwenClient


def _mock_plan(request: PosterRequest) -> PosterPlan:
    has_sources = bool(request.source_text.strip())
    return PosterPlan(
        task_id=str(uuid4()),
        mode="mock",
        status="needs_human_review" if has_sources else "needs_sources",
        title=f"看见科学：{request.topic}",
        subtitle="从权威证据到公众可理解的视觉叙事",
        audience=request.audience,
        aspect_ratio=request.aspect_ratio,
        fact_cards=[
            FactCard(
                claim_id="C-001",
                claim="Mock模式不生成未经证据支持的科学事实。",
                evidence_status="missing" if not has_sources else "supported",
                evidence=[],
                caveat="接入百炼知识库或提供权威资料后生成真实事实卡。",
            )
        ],
        sections=[
            PosterSection(
                heading="一个核心问题",
                purpose="用一句公众能够理解的问题建立阅读动机",
                visual_form="主视觉＋短标题",
                content_summary=f"围绕“{request.topic}”建立单一视觉焦点。",
            ),
            PosterSection(
                heading="机制如何发生",
                purpose="用三到五步解释关键过程",
                visual_form="可编辑SVG流程图",
                content_summary="等待权威资料后确定实体、顺序、箭头和条件。",
            ),
            PosterSection(
                heading="证据与边界",
                purpose="呈现来源并说明科学结论的适用范围",
                visual_form="证据卡＋来源二维码区",
                content_summary="所有核心陈述与source_id逐条对应。",
            ),
        ],
        visual_direction=f"{request.visual_style}；{request.aspect_ratio}竖版优先；主视觉单一；避免信息拥挤。",
        missing_information=[] if has_sources else ["至少一份权威科学资料或经过审核的资料摘录"],
        safety_note="当前为Mock演示，不可将占位内容作为最终科学作品提交。",
    )


async def create_poster_plan(request: PosterRequest) -> PosterPlan:
    if settings.mock_ai:
        return _mock_plan(request)

    effective_request = request
    retrieval: KnowledgeAnswer | None = None
    if not request.source_text.strip() and settings.app_id:
        retrieval = await BailianKnowledgeAppClient(settings).query(request.topic)
        if retrieval.status == "insufficient_evidence":
            plan = _mock_plan(request)
            return plan.model_copy(
                update={
                    "mode": "bailian",
                    "retrieval_status": retrieval.status,
                    "retrieval_max_score": retrieval.max_retrieval_score,
                    "source_documents": [
                        reference.doc_name
                        for reference in retrieval.references
                        if reference.doc_name
                    ],
                    "safety_note": retrieval.answer,
                }
            )
        effective_request = request.model_copy(
            update={"source_text": _retrieval_source_text(retrieval)}
        )

    raw = await QwenClient(settings).create_poster_plan(effective_request)
    for reserved_key in (
        "task_id",
        "mode",
        "retrieval_status",
        "retrieval_max_score",
        "source_documents",
    ):
        raw.pop(reserved_key, None)
    return PosterPlan(
        task_id=str(uuid4()),
        mode="bailian",
        retrieval_status=retrieval.status if retrieval else "user_sources",
        retrieval_max_score=retrieval.max_retrieval_score if retrieval else None,
        source_documents=(
            list(dict.fromkeys(
                reference.doc_name
                for reference in retrieval.references
                if reference.score >= retrieval.threshold and reference.doc_name
            ))
            if retrieval
            else []
        ),
        **raw,
    )


def _retrieval_source_text(retrieval: KnowledgeAnswer) -> str:
    blocks: list[str] = []
    for reference in retrieval.references:
        if reference.score < retrieval.threshold:
            continue
        blocks.append(
            "\n".join(
                [
                    f"[检索证据 {reference.index_id}]",
                    f"文档名：{reference.doc_name}",
                    f"文档ID：{reference.doc_id}",
                    f"检索分数：{reference.score:.6f}",
                    f"正文：{reference.text}",
                ]
            )
        )
    return "\n\n".join(blocks)
