from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
PLAN_PATH = PROJECT_ROOT / "artifacts" / "solar-weather-poster-plan-v1.json"

sys.path.insert(0, str(BACKEND_ROOT))

from app.models import PosterPlan, ReviewIssue, RevisionRequest  # noqa: E402
from app.services.visual_workflow import (  # noqa: E402
    build_revision_plan,
    build_video_storyboard,
    build_visual_asset_bundle,
)


def main() -> None:
    plan = PosterPlan.model_validate(json.loads(PLAN_PATH.read_text(encoding="utf-8")))
    assets = build_visual_asset_bundle(plan)
    storyboard = build_video_storyboard(plan)
    revision = build_revision_plan(
        RevisionRequest(
            task_id=plan.task_id,
            current_version=1,
            issues=[
                ReviewIssue(
                    issue_id="UI-001",
                    target_id="poster-source-block",
                    category="readability",
                    severity="minor",
                    description="小屏预览时来源区字号较小。",
                    suggested_fix="将来源区最小字号提高并增加行距，不改变来源内容。",
                )
            ],
        )
    )
    print(
        json.dumps(
            {
                "visual_assets": len(assets.assets),
                "asset_manifest": assets.manifest_path,
                "video_scenes": len(storyboard.scenes),
                "storyboard_manifest": storyboard.manifest_path,
                "revision_status": revision.status,
                "revision_manifest": revision.manifest_path,
                "paid_model_called": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

