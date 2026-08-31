"""One explicit follow-up round on the two real test projects; preserves all drafts.
This is developer review feedback, not a fabricated independent user evaluation.
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.studio_models import RunInput
from app.services import studio_store as store
from app.services.studio_pipeline import execute
from app.services.studio_export import export_zip


async def main():
    directory = ROOT / "evidence/studio-v020"
    old = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    report = []
    for item in old:
        p = store.get_project(item["project"])
        feedback = (
            "开发者复核反馈：不能从统计预测机制推导‘AI不是靠理解事实’等哲学判断；来源没有这种断言。"
            "天气百分比、具体年份的虚构事件都不需要，换成不含具体数字的清楚类比，并标注类比不是机制。"
            if "AI" in p["input"]["topic"] else
            "开发者复核反馈：当前来源只说明策略建议，并未提供与被动重读的直接比较数据，删除‘比被动重读更好’等比较。"
            "去掉‘两三天’等固定复习时间，不能让人误以为是人人通用的最佳间隔。所有镜头、事实和图解一起检查。"
        )
        r = RunInput(request_id=uuid4(), expected_version=p["versions"][-1]["version"], feedback=feedback)
        store.reserve(p["id"], r)
        print(json.dumps({"phase":"refine", "project":p["id"]}), flush=True)
        await execute(p["id"], r)
        result = store.get_project(p["id"])
        v = result["versions"][-1]
        filename = f"{p['id']}-v{v['version']}"
        (directory / (filename + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / (filename + '.zip')).write_bytes(export_zip(result))
        entry = {"project":p["id"], "version":v["version"], "state":result["runs"][-1]["state"],
                 "review_status":v["review_status"], "changes":len(v["changes"]), "findings":v["findings"]}
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (directory / f"refined-{datetime.now():%Y%m%d-%H%M%S}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__": asyncio.run(main())
