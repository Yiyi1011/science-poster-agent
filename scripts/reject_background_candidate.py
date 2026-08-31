from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKFLOW_ROOT = PROJECT_ROOT / "artifacts" / "workflow"

sys.path.insert(0, str(BACKEND_ROOT))

from app.models import ReviewIssue, RevisionRequest, VisualAssetBundle  # noqa: E402
from app.services.visual_workflow import build_revision_plan, persist_version  # noqa: E402


def main() -> None:
    candidates = sorted(
        WORKFLOW_ROOT.glob("*/visual-assets-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    envelope = json.loads(candidates[0].read_text(encoding="utf-8"))
    bundle = VisualAssetBundle.model_validate(envelope["payload"])
    background = next(
        asset for asset in bundle.assets if asset.asset_type == "context_background"
    )
    issue = ReviewIssue(
        issue_id="VR-005",
        target_id=background.asset_id,
        category="readability",
        severity="major",
        description="背景候选仍生成大段伪文字和信息图面板，无法作为纯背景图层。",
        evidence_claim_ids=background.source_claim_ids,
        suggested_fix="拒绝该候选；正式主案例暂用可编辑SVG背景，不再自动消耗生图预算。",
    )
    review_manifest = persist_version(
        bundle.task_id,
        "visual-review",
        {
            "reviewer": "human_visual_inspection",
            "candidate_version": background.version,
            "decision": "reject_and_stop_paid_generation",
            "issues": [issue.model_dump()],
            "recorded_image_cost_cny": 0.54,
        },
    )
    revision = build_revision_plan(
        RevisionRequest(task_id=bundle.task_id, current_version=3, issues=[issue])
    )
    updated_assets = [
        asset.model_copy(update={"status": "rejected"})
        if asset.asset_id == background.asset_id
        else asset
        for asset in bundle.assets
    ]
    updated_bundle = bundle.model_copy(
        update={"assets": updated_assets, "status": "needs_review"}
    )
    bundle_manifest = persist_version(
        bundle.task_id,
        "visual-assets",
        updated_bundle.model_dump(exclude={"manifest_path"}),
    )
    print(
        json.dumps(
            {
                "background_status": "rejected",
                "review_manifest": review_manifest,
                "revision_manifest": revision.manifest_path,
                "bundle_manifest": bundle_manifest,
                "additional_paid_call": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
