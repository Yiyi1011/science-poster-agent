from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models import EvidenceRef, PosterPlan  # noqa: E402
from app.services.svg_renderer import render_poster_svg  # noqa: E402


def write_reviewed_plan(slug: str, plan: PosterPlan) -> None:
    output_dir = PROJECT_ROOT / "artifacts" / "cross-topic" / slug
    (output_dir / "poster-plan-v004-final.json").write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "poster-v004-final.svg").write_text(
        render_poster_svg(plan),
        encoding="utf-8",
    )


def review_ai() -> None:
    slug = "ai-confabulation"
    path = PROJECT_ROOT / "artifacts" / "cross-topic" / slug / "poster-plan-v001.json"
    plan = PosterPlan.model_validate_json(path.read_text(encoding="utf-8"))
    plan.title = "AI为什么会“说得像真的”？"
    plan.subtitle = "生成不等于核验：给回答做三层检查"
    plan.fact_cards[0].caveat = "这是面向公众的机制概括；模型结构与训练方式并不完全相同。"
    plan.fact_cards[1].caveat = "这不是主观欺骗；NIST将此类错误或矛盾输出归为confabulation风险。"
    plan.sections[0].visual_form = "左侧回答气泡：只展示‘表达流畅’，不放置未经证据支持的科学例句"
    plan.sections[0].content_summary = "模型生成连贯文本，但流畅、完整和自信的语气不等于事实已被验证。"
    plan.sections[1].content_summary = "查验来源是否真实、可访问，并逐项核对关键数字、条件和因果关系。"
    plan.sections[2].visual_form = "右侧结论框：标注‘待专业复核’或‘已核验’，不得默认宣称已经核验"
    plan.sections[2].content_summary = "教育等高影响场景应保留合格人员的判断与责任。"
    plan.safety_note = "不把模型拟人化为故意欺骗；检索和引用可以辅助核验，但不能保证输出正确。"
    write_reviewed_plan(slug, plan)


def review_education() -> None:
    slug = "retrieval-practice"
    path = PROJECT_ROOT / "artifacts" / "cross-topic" / slug / "poster-plan-v001.json"
    plan = PosterPlan.model_validate_json(path.read_text(encoding="utf-8"))
    plan.title = "为什么主动回忆更容易记牢？"
    plan.subtitle = "别只重复看：练习在需要时把知识提取出来"
    source_ids = (
        ("EDU-001", "EDU-002", "EDU-003"),
        ("EDU-001",),
        ("EDU-003", "EDU-004"),
    )
    for card, ids in zip(plan.fact_cards, source_ids, strict=True):
        card.evidence = [EvidenceRef(source_id=value, locator="来源台账") for value in ids]
    plan.fact_cards[2].claim = "一个可执行闭环：主动回忆、核对纠错、间隔再练。"
    plan.fact_cards[2].caveat = "这是综合证据后的实践建议；不能替代初次理解、讲解和支持性反馈。"
    plan.sections[0].content_summary = "比较再次接触材料与主动提取：熟悉感不等于延迟后仍能回忆。"
    plan.sections[1].heading = "低压力自测，不是高风险考试"
    plan.sections[1].purpose = "消解对测试的单一负面联想，明确活动边界"
    plan.sections[1].visual_form = "桥梁隐喻：桥墩标注‘回忆’‘核对纠错’‘间隔’，明确这是艺术化表达"
    plan.sections[1].content_summary = "目标是练习提取并发现知识缺口，不用于给学习者贴标签或制造惩罚。"
    plan.sections[2].visual_form = "三步卡片：①合上资料主动回忆；②对照原文纠错；③间隔一段时间后再练"
    plan.sections[2].content_summary = "给出不含固定天数和提升比例的可操作步骤。"
    plan.safety_note = "检索练习是总体有效趋势而非普遍保证；不等于高风险考试，也不能替代理解、讲解和反馈。"
    write_reviewed_plan(slug, plan)


if __name__ == "__main__":
    review_ai()
    review_education()
    print("reviewed cross-topic poster plans written as v004-final")
