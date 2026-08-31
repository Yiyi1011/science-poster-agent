from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.services.bailian_app_client import BailianKnowledgeAppClient  # noqa: E402


async def main() -> None:
    question_id = sys.argv[1] if len(sys.argv) > 1 else "RT-011"
    questions = {
        "RT-011": "所有X级耀斑都会伴随CME吗？",
        "RT-022": "下一次太阳风暴会在北京造成多少亿元损失？",
    }
    question = questions.get(question_id)
    if question is None:
        raise SystemExit(f"Unsupported safe verification case: {question_id}")
    try:
        result = await BailianKnowledgeAppClient(settings).query(question)
    except httpx.HTTPStatusError as exc:
        try:
            error_body = exc.response.json()
        except ValueError:
            error_body = {}
        safe_error = {
            "http_result": "failed",
            "status_code": exc.response.status_code,
            "error_code": str(error_body.get("code") or ""),
            "error_message": str(error_body.get("message") or "")[:300],
            "request_id": str(error_body.get("request_id") or ""),
            "secret_recorded": False,
            "response_body_recorded": False,
        }
        print(json.dumps(safe_error, ensure_ascii=False, indent=2))
        return
    safe = {
        "http_result": "success",
        "question_id": question_id,
        "status": result.status,
        "answer_characters": len(result.answer),
        "reference_count": len(result.references),
        "reference_doc_names": sorted(
            {reference.doc_name for reference in result.references if reference.doc_name}
        ),
        "max_retrieval_score": result.max_retrieval_score,
        "threshold": result.threshold,
        "gate_reason": result.gate_reason,
        "session_id_recorded": bool(result.session_id),
        "request_id": result.request_id,
        "secret_recorded": False,
        "answer_recorded": False,
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
