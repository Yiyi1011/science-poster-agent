from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKFLOW_ROOT = PROJECT_ROOT / "artifacts" / "workflow"
TASK_ID = "e227ed71-e128-4ae7-9da4-a0db070e56b3"

sys.path.insert(0, str(BACKEND_ROOT))

from app.services.visual_workflow import persist_version  # noqa: E402


def main() -> None:
    review_path = WORKFLOW_ROOT / TASK_ID / "vision-review-v001.json"
    envelope = json.loads(review_path.read_text(encoding="utf-8"))
    issues = envelope["payload"]["review"]["issues"]
    accepted_ids = {"i-01", "i-02", "i-03", "i-05", "i-06"}
    decisions = []
    for issue in issues:
        accepted = issue["issue_id"] in accepted_ids
        reason = (
            "属于可验证的版式、可读性或品牌中性化问题；仅修改SVG表现层。"
            if accepted
            else "拒绝加入模型建议的新时间数值；当前事实卡只支持既有范围，不能越过证据契约。"
        )
        decisions.append({**issue, "accepted": accepted, "adjudication_reason": reason})
    manifest = persist_version(
        TASK_ID,
        "vision-review-adjudication",
        {
            "source_review": "vision-review-v001.json",
            "accepted_issue_ids": sorted(accepted_ids),
            "rejected_issue_ids": ["i-04"],
            "decisions": decisions,
            "applied_to": "solar-weather-poster-v2.svg",
            "human_adjudication": True,
            "new_scientific_numbers_added": False,
        },
    )
    print(
        json.dumps(
            {
                "accepted": len(accepted_ids),
                "rejected": 1,
                "manifest_path": manifest,
                "new_scientific_numbers_added": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
