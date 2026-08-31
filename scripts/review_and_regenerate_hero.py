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


def newest_bundle() -> tuple[Path, VisualAssetBundle]:
    candidates = sorted(
        WORKFLOW_ROOT.glob("*/visual-assets-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("No visual asset bundle exists.")
    path = candidates[0]
    envelope = json.loads(path.read_text(encoding="utf-8"))
    return path, VisualAssetBundle.model_validate(envelope["payload"])


async def main() -> None:
    _, bundle = newest_bundle()
    hero = next(asset for asset in bundle.assets if asset.asset_type == "hero_illustration")

    issues = [
        ReviewIssue(
            issue_id="VR-001",
            target_id=hero.asset_id,
            category="readability",
            severity="major",
            description="候选图生成了大量不可辨识的伪文字，不能进入正式海报。",
            evidence_claim_ids=hero.source_claim_ids,
            suggested_fix="改为纯插画层，禁止信息图面板、标题、标签、数字和任何字符。",
        ),
        ReviewIssue(
            issue_id="VR-002",
            target_id=hero.asset_id,
            category="fact",
            severity="critical",
            description="只绑定耀斑电磁辐射的资产混入SEP和CME，超出该事实卡范围。",
            evidence_claim_ids=hero.source_claim_ids,
            suggested_fix="仅保留太阳、电磁波、地球向阳面和电离层吸收的空间关系。",
        ),
    ]
    review_manifest = persist_version(
        bundle.task_id,
        "visual-review",
        {
            "reviewer": "human_visual_inspection",
            "candidate_version": hero.version,
            "decision": "regenerate_once",
            "issues": [issue.model_dump() for issue in issues],
            "automatic_candidate_limit": bundle.max_candidates_per_asset,
        },
    )
    revision = build_revision_plan(
        RevisionRequest(task_id=bundle.task_id, current_version=1, issues=issues)
    )

    revised = hero.model_copy(
        update={
            "version": 2,
            "status": "planned",
            "prompt": (
                "Pure full-bleed scientific editorial illustration, NOT an infographic. "
                "Portrait 3:4 composition on deep space blue. Show one physically recognizable Sun "
                "near the upper left and one Earth near the lower right. A restrained fan of luminous "
                "electromagnetic waves travels from the Sun to the sunlit hemisphere of Earth. "
                "Show a thin atmospheric rim with subtle absorption on the dayside ionosphere. "
                "Large calm negative space for later vector typography. Precise, elegant Nature/Science "
                "editorial art, realistic scale cues without pretending objects are to scale. "
                "Absolutely no text, no letters, no numbers, no symbols, no arrows, no labels, no legend, "
                "no panels, no timeline, no interface, no watermark. Do not show SEP particle streams, "
                "CME plasma clouds, geomagnetic storm, city disaster, explosions, satellites or astronauts."
            ),
            "negative_prompt": (
                "typography, Chinese characters, English letters, numbers, captions, labels, legend, "
                "infographic layout, UI panels, timeline, SEP, CME, plasma cloud, geomagnetic storm, "
                "disaster movie, city explosion, fictional data, logo, watermark"
            ),
        }
    )
    output_dir = WORKFLOW_ROOT / bundle.task_id / "assets"
    before_cost = recorded_image_cost()
    result = await QwenImageClient(settings).generate(revised, output_dir)

    updated_assets = [
        result.asset if asset.asset_id == hero.asset_id else asset
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
                "status": "needs_review",
                "review_manifest": review_manifest,
                "revision_manifest": revision.manifest_path,
                "candidate_version": result.asset.version,
                "file_path": result.asset.file_path,
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
