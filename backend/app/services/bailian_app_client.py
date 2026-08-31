from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import KnowledgeAnswer, KnowledgeReference
from app.services.usage_ledger import record_retrieval_usage


def workspace_origin(settings: Settings) -> str:
    """Return the workspace-specific origin required by the knowledge gateway."""
    parsed = urlparse(settings.dashscope_base_url)
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme}://{parsed.netloc}"
    raise RuntimeError("DASHSCOPE_BASE_URL must be a full workspace-specific URL.")


def parse_retrieval_response(body: dict[str, Any], threshold: float) -> KnowledgeAnswer:
    data = body.get("data") or {}
    raw_nodes = data.get("nodes") or []
    references: list[KnowledgeReference] = []
    for index, node in enumerate(raw_nodes, start=1):
        if not isinstance(node, dict):
            continue
        metadata = node.get("metadata") or {}
        score = float(node.get("score") or metadata.get("_score_with_weight") or 0)
        references.append(
            KnowledgeReference(
                index_id=str(index),
                title=str(metadata.get("title") or metadata.get("hier_title") or ""),
                doc_id=str(metadata.get("doc_id") or ""),
                doc_name=str(metadata.get("doc_name") or ""),
                text=str(node.get("text") or metadata.get("content") or ""),
                score=score,
            )
        )

    references.sort(key=lambda item: item.score, reverse=True)
    max_score = references[0].score if references else None
    if max_score is None or max_score < threshold:
        status = "insufficient_evidence"
        answer = "现有知识库证据不足，无法形成可靠结论。请补充权威资料后再试。"
        gate_reason = "no_result_or_score_below_threshold"
    else:
        status = "supported"
        answer = "已检索到达到证据阈值的知识切片，可进入事实卡生成与科学审核。"
        gate_reason = "retrieval_score_passed"

    return KnowledgeAnswer(
        status=status,
        answer=answer,
        references=references,
        max_retrieval_score=max_score,
        threshold=threshold,
        gate_reason=gate_reason,
        request_id=str(body.get("request_id") or ""),
    )


class BailianKnowledgeAppClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def query(self, question: str, session_id: str = "") -> KnowledgeAnswer:
        del session_id  # Retrieval services are stateless; kept for API compatibility.
        self.settings.validate_for_knowledge_app()
        payload = {
            "query": question,
            "agent_id": self.settings.app_id,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{workspace_origin(self.settings)}/api/v1/indices/knowledge/search"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        body = response.json()
        result = parse_retrieval_response(body, self.settings.retrieval_min_score)
        record_retrieval_usage(
            self.settings,
            request_id=result.request_id,
            result_count=len(result.references),
            max_score=result.max_retrieval_score,
            purpose="knowledge_retrieval",
        )
        return result
