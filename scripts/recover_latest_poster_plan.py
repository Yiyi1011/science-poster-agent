from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models import PosterPlan  # noqa: E402


def main() -> None:
    candidates = sorted(
        (PROJECT_ROOT / "artifacts" / "raw").glob("qwen-poster-plan-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("No saved raw poster plan found.")
    raw = json.loads(candidates[0].read_text(encoding="utf-8"))
    plan = PosterPlan(
        task_id=str(uuid4()),
        mode="bailian",
        retrieval_status="supported",
        retrieval_max_score=0.7166596055030823,
        source_documents=[
            "01_太阳爆发与三类信使",
            "02_通信导航与条件边界",
        ],
        **raw,
    )
    output_path = PROJECT_ROOT / "artifacts" / "solar-weather-poster-plan-v1.json"
    output_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "recovered",
                "artifact": str(output_path.relative_to(PROJECT_ROOT)),
                "title": plan.title,
                "fact_cards": len(plan.fact_cards),
                "supported_facts": sum(
                    card.evidence_status == "supported" for card in plan.fact_cards
                ),
                "sections": len(plan.sections),
                "additional_model_call": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
