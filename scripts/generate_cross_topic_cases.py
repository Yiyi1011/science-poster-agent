from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.models import PosterPlan, PosterRequest  # noqa: E402
from app.services.pipeline import create_poster_plan  # noqa: E402
from app.services.svg_renderer import render_poster_svg  # noqa: E402


CASES = (
    {
        "slug": "ai-confabulation",
        "topic": "为什么生成式AI会产生看似可信的错误？",
        "style": "现代科学信息图；用回答气泡穿过证据筛网表现生成、核验与人工复核；品牌中立；避免拟人化",
        "recover_raw": "artifacts/raw/qwen-poster-plan-20260829-205911.json",
    },
    {
        "slug": "retrieval-practice",
        "topic": "为什么主动回忆通常比反复重读更利于长期记忆？",
        "style": "现代教育科学信息图；两条并行学习路径；突出回忆、反馈、间隔再练；避免无证据脑区图",
    },
)


async def generate_case(case: dict[str, str]) -> dict[str, object]:
    case_dir = PROJECT_ROOT / "cross-topic-cases" / case["slug"]
    evidence_path = case_dir / "evidence-brief.md"
    source_path = case_dir / "source-ledger.md"
    source_text = "\n\n".join(
        (
            evidence_path.read_text(encoding="utf-8"),
            source_path.read_text(encoding="utf-8"),
        )
    )
    request = PosterRequest(
        topic=case["topic"],
        audience="普通公众",
        source_text=source_text,
        visual_style=case["style"],
        aspect_ratio="3:4",
    )
    recover_raw = case.get("recover_raw", "")
    if recover_raw:
        raw = json.loads((PROJECT_ROOT / recover_raw).read_text(encoding="utf-8"))
        plan = PosterPlan(
            task_id="cross-ai-confabulation-v001",
            mode="bailian",
            retrieval_status="user_sources",
            retrieval_max_score=None,
            source_documents=[],
            **raw,
        )
    else:
        plan = await create_poster_plan(request)

    output_dir = PROJECT_ROOT / "artifacts" / "cross-topic" / case["slug"]
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "poster-plan-v001.json"
    svg_path = output_dir / "poster-v001.svg"
    manifest_path = output_dir / "generation-manifest-v001.json"
    plan_path.write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    svg_path.write_text(render_poster_svg(plan), encoding="utf-8")
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "case": case["slug"],
        "provider": "Alibaba Cloud Model Studio",
        "base_model": "Qwen",
        "input_route": "local_authoritative_source_text",
        "new_knowledge_base_created": False,
        "paid_image_or_video_model_used": False,
        "human_science_review_required": True,
        "inputs": [
            str(evidence_path.relative_to(PROJECT_ROOT)),
            str(source_path.relative_to(PROJECT_ROOT)),
        ],
        "outputs": [
            str(plan_path.relative_to(PROJECT_ROOT)),
            str(svg_path.relative_to(PROJECT_ROOT)),
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "case": case["slug"],
        "task_id": plan.task_id,
        "status": plan.status,
        "fact_cards": len(plan.fact_cards),
        "plan": str(plan_path),
        "svg": str(svg_path),
    }


async def main() -> None:
    results = []
    for case in CASES:
        results.append(await generate_case(case))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
