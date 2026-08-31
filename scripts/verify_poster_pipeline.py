from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models import PosterRequest  # noqa: E402
from app.services.pipeline import create_poster_plan  # noqa: E402


async def main() -> None:
    request = PosterRequest(
        topic="太阳按下‘干扰键’之后：8分钟到几天的空间天气接力",
        audience="普通公众",
        source_text="",
        visual_style="Nature/Science风格的科学信息海报，严谨、清晰、有主视觉",
        aspect_ratio="3:4",
    )
    plan = await create_poster_plan(request)
    output_path = PROJECT_ROOT / "artifacts" / "solar-weather-poster-plan-v1.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        plan.model_dump_json(indent=2),
        encoding="utf-8",
    )
    safe = {
        "http_result": "success",
        "case_id": "SOLAR-WEATHER-HERO-v1",
        "mode": plan.mode,
        "status": plan.status,
        "title": plan.title,
        "retrieval_status": plan.retrieval_status,
        "retrieval_max_score": plan.retrieval_max_score,
        "source_documents": plan.source_documents,
        "fact_card_count": len(plan.fact_cards),
        "supported_fact_count": sum(
            card.evidence_status == "supported" for card in plan.fact_cards
        ),
        "section_count": len(plan.sections),
        "missing_information_count": len(plan.missing_information),
        "safety_note_recorded": bool(plan.safety_note),
        "task_id": plan.task_id,
        "artifact_path": str(output_path.relative_to(PROJECT_ROOT)),
        "secret_recorded": False,
        "source_excerpts_recorded": False,
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        failure_path = PROJECT_ROOT / "artifacts" / "poster-pipeline-last-error.txt"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(traceback.format_exc(), encoding="utf-8")
        print(
            json.dumps(
                {
                    "http_result": "failed_after_model_call",
                    "error_type": type(exc).__name__,
                    "error_saved": str(failure_path.relative_to(PROJECT_ROOT)),
                    "secret_recorded": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)
