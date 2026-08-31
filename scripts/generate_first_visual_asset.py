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
from app.models import VisualAssetBundle  # noqa: E402
from app.services.qwen_image_client import QwenImageClient  # noqa: E402
from app.services.usage_ledger import recorded_image_cost  # noqa: E402
from app.services.visual_workflow import persist_version  # noqa: E402


def newest_asset_manifest() -> Path:
    candidates = sorted(
        WORKFLOW_ROOT.glob("*/visual-assets-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("No visual asset manifest exists. Run bootstrap_visual_workflow.py first.")
    return candidates[0]


async def main() -> None:
    source_path = newest_asset_manifest()
    envelope = json.loads(source_path.read_text(encoding="utf-8"))
    bundle = VisualAssetBundle.model_validate(envelope["payload"])
    pending = next((asset for asset in bundle.assets if asset.status == "planned"), None)
    if pending is None:
        raise RuntimeError("No planned asset is available for generation.")

    before_cost = recorded_image_cost()
    output_dir = WORKFLOW_ROOT / bundle.task_id / "assets"
    result = await QwenImageClient(settings).generate(pending, output_dir)

    updated_assets = [
        result.asset if asset.asset_id == pending.asset_id else asset
        for asset in bundle.assets
    ]
    updated_bundle = bundle.model_copy(
        update={
            "assets": updated_assets,
            "status": "partially_ready",
        }
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
                "model": result.asset.model,
                "asset_id": result.asset.asset_id,
                "file_path": result.asset.file_path,
                "output_count": result.output_count,
                "estimated_call_cost_cny": result.estimated_cost_cny,
                "recorded_image_cost_before_cny": before_cost,
                "recorded_image_cost_after_cny": recorded_image_cost(),
                "image_sub_budget_cny": settings.image_generation_budget_cny,
                "generation_manifest": result.manifest_path,
                "bundle_manifest": bundle_manifest,
                "secret_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
