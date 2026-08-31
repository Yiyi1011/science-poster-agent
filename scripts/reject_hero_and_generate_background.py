from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKFLOW_ROOT = PROJECT_ROOT / "artifacts" / "workflow"

sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.models import ReviewIssue, RevisionRequest, VisualAssetBundle  # noqa: E402
from app.services.qwen_image_client import QwenImageClient  # noqa: E402
from app.services.usage_ledger import recorded_image_cost  # noqa: E402
from app.services.visual_workflow import build_revision_plan, persist_version  # noqa: E402


def load_latest_bundle() -> VisualAssetBundle:
    candidates = sorted(
        WORKFLOW_ROOT.glob("*/visual-assets-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("No visual asset bundle exists.")
    envelope = json.loads(candidates[0].read_text(encoding="utf-8"))
    return VisualAssetBundle.model_validate(envelope["payload"])


async def main() -> None:
    bundle = load_latest_bundle()
    hero = next(asset for asset in bundle.assets if asset.asset_type == "hero_illustration")
    background = next(
        asset for asset in bundle.assets if asset.asset_type == "context_background"
    )

    issues = [
        ReviewIssue(
            issue_id="VR-003",
            target_id=hero.asset_id,
            category="copyright",
            severity="critical",
            description="候选2生成了期刊品牌字样和大量伪排版，不可进入参赛成品。",
            evidence_claim_ids=hero.source_claim_ids,
            suggested_fix="停止该资产自动生图，回退到可编辑SVG科学绘图。",
        ),
        ReviewIssue(
            issue_id="VR-004",
            target_id=hero.asset_id,
            category="fact",
            severity="critical",
            description="候选2仍混入SEP面板，超出耀斑电磁辐射事实卡范围。",
            evidence_claim_ids=hero.source_claim_ids,
            suggested_fix="主视觉仅采用经人工核验的SVG太阳、地球和电磁波图层。",
        ),
    ]
    review_manifest = persist_version(
        bundle.task_id,
        "visual-review",
        {
            "reviewer": "human_visual_inspection",
            "candidate_version": hero.version,
            "decision": "reject_and_fallback_to_svg",
            "issues": [issue.model_dump() for issue in issues],
            "paid_candidates_used_for_asset": 2,
            "automatic_candidate_limit": bundle.max_candidates_per_asset,
        },
    )
    revision = build_revision_plan(
        RevisionRequest(task_id=bundle.task_id, current_version=2, issues=issues)
    )
    rejected_hero = hero.model_copy(update={"status": "rejected"})

    revised_background = background.model_copy(
        update={
            "prompt": (
                "Full-bleed abstract astrophysics background, portrait 3:4. Deep navy space with a "
                "single small Earth near the lower third. Subtle translucent magnetosphere field arcs "
                "surround Earth and a restrained warm plasma glow approaches from the left without impact. "
                "Large dark negative space, low visual density, scientifically sober, elegant volumetric "
                "light, suitable behind a separate vector infographic layer. Pure image only. "
                "No text, no letters, no numbers, no symbols, no arrows, no diagrams, no panels, no logos, "
                "no watermark, no brand imitation, no city disaster, no explosion."
            ),
            "negative_prompt": (
                "typography, captions, labels, legend, infographic, UI, interface, timeline, icons, "
                "brand, magazine cover, logo, watermark, disaster, explosion, burning Earth, fictional data"
            ),
        }
    )
    before_cost = recorded_image_cost()
    result = await QwenImageClient(settings).generate(
        revised_background,
        WORKFLOW_ROOT / bundle.task_id / "assets",
    )
    updated_assets = [
        rejected_hero
        if asset.asset_id == hero.asset_id
        else result.asset
        if asset.asset_id == background.asset_id
        else asset
        for asset in bundle.assets
    ]
    updated_bundle = bundle.model_copy(
        update={"assets": updated_assets, "status": "partially_ready"}
    )
    bundle_manifest = persist_version(
        bundle.task_id,
        "visual-assets",
        updated_bundle.model_dump(exclude={"manifest_path"}),
    )
    print(
        json.dumps(
            {
                "hero_status": "rejected",
                "review_manifest": review_manifest,
                "revision_manifest": revision.manifest_path,
                "background_status": "needs_review",
                "background_file_path": result.asset.file_path,
                "estimated_call_cost_cny": result.estimated_cost_cny,
                "recorded_image_cost_before_cny": before_cost,
                "recorded_image_cost_after_cny": recorded_image_cost(),
                "bundle_manifest": bundle_manifest,
                "secret_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
