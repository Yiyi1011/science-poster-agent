from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
PLAN_PATH = PROJECT_ROOT / "artifacts" / "solar-weather-poster-plan-v1.json"
IMAGE_PATH = PROJECT_ROOT / "artifacts" / "solar-weather-poster-v2.png"

sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.models import PosterPlan  # noqa: E402
from app.services.qwen_vision_reviewer import QwenVisionReviewer  # noqa: E402


async def main() -> None:
    plan = PosterPlan.model_validate(json.loads(PLAN_PATH.read_text(encoding="utf-8")))
    result = await QwenVisionReviewer(settings).review(IMAGE_PATH, plan)
    review = result["review"]
    output = json.dumps(
            {
                "status": review.get("status"),
                "scores": review.get("scores"),
                "issue_count": len(review.get("issues") or []),
                "issues": review.get("issues"),
                "summary": review.get("summary"),
                "estimated_cost_cny": result["estimated_cost_cny"],
                "manifest_path": result["manifest_path"],
                "human_review_required": True,
                "secret_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))


if __name__ == "__main__":
    asyncio.run(main())
