"""Deterministic, honest fallbacks when the Qwen planning/repair chain fails.

Brief section 6.4.6: instead of pretending model planning succeeded, persist an
explicit local six-shot template whose sentences state it is an unverified
template draft, then continue so a human can repair it. Claims and scene text
are organized from the already-reviewed source excerpts (quotes stay locatable);
nothing is invented. The fallback flag must never be misrepresented as model output.
"""
from __future__ import annotations

import re


def _sentences(text):
    return [part.strip() for part in re.split(r"(?<=[。！？!?])", text or "") if part.strip()]


def _cut(text, limit):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _source_quote(text):
    for sentence in _sentences(text):
        if len(sentence) >= 12:
            return sentence[:500]
    return (text or "")[:60]


FALLBACK_SCENES = [
    ("提出问题", "hook"),
    ("具体情境", "example"),
    ("展开机制", "mechanism"),
    ("逐步说明", "process"),
    ("保留边界", "boundary"),
    ("记住要点", "takeaway"),
]

VISUALS = [
    "卡通人物翻看资料卡，问号标记提示这是待核验的模板初稿。",
    "把原句显示在画面中央，箭头指向可核对的来源。",
    "翻开第一份资料的原文，按顺序显示机制文字。",
    "翻开第二份资料与第一份对照，标出相同与不同。",
    "出现边界框，把资料写明和没写明的部分分开。",
    "收束成一句话，旁边列出可核对的来源清单。",
]

_TEMPLATE_NOTE = "本稿由本地确定性模板组织，未经模型审核与专家终审"


def deterministic_fallback_draft(data, primer_answer=""):
    """Six-shot template draft organized from already-reviewed sources."""
    from app.studio_models import StudioDraft

    claims, ids = [], []
    for index, source in enumerate(data.sources[:4], 1):
        quote = _source_quote(source.text)
        claim_id = f"C{index}"
        claims.append({"claim_id": claim_id, "text": _cut(quote, 160), "source_id": source.source_id,
                       "quote": quote, "boundary": "模板摘录：资料原文范围内，未经模型审核与科学终审"})
        ids.append(claim_id)
    primary = ids[0]
    scenes = []
    for index, (heading, role) in enumerate(FALLBACK_SCENES, 1):
        if role == "mechanism":
            narration = "按资料的顺序讲机制：" + _cut(claims[0]["text"], 79)
        elif role == "process":
            narration = "再看第二份资料：" + (_cut(claims[1]["text"], 79) if len(claims) > 1 else "再对照别的说法，检查有没有遗漏。")
        elif role == "boundary":
            narration = "边界：" + _TEMPLATE_NOTE + "；资料没有写明的细节，不要当作已核实的结论。"
        elif role == "takeaway":
            narration = "记住：每条事实都带可定位来源和适用范围；未核实之处会在后续修订中补齐，可在证据页逐条核对。"
        elif role == "example":
            narration = "先读资料原文，再看它能直接回答什么问题。例子保留原句，方便对照核验。"
        else:
            narration = f"你问的是：{_cut(data.topic, 24)}。先用公开资料回答，这一版仍是未核验的模板初稿。"
        scenes.append({"scene_id": f"V{index}", "role": role, "heading": heading, "narration": narration,
                       "visual_action": VISUALS[index - 1], "claim_ids": [primary]})
    answer = primer_answer or ""
    draft = StudioDraft.model_validate({
        "title": _cut(data.topic, 24), "takeaway": "这一版是本地模板初稿，尚未经模型审核；请人工核对每条摘录后再当作结论。",
        "claims": claims, "diagram": {"kind": "sequence", "labels": ["读资料", "核来源", "留边界"],
                                      "caption": "模板示意：未核实初稿的整理流程，不是科学机制"},
        "scenes": scenes,
        "public_poster": {
            "cards": [{"heading": "模板初稿", "body": "这份作品由本地模板整理，不是模型已核实的成品。", "claim_ids": [primary]},
                      {"heading": "摘录可查", "body": "每条事实都指向可打开核对的原文摘录，边界写明适用范围。", "claim_ids": [primary]}],
            "example": {"heading": "举例", "body": "例如用第一份资料的原句回答提问，句子保留在证据页可核对。", "claim_ids": [primary]},
            "caution": {"heading": "注意", "body": "资料没有写明的内容，不要当作已核实的结论使用。", "claim_ids": [primary]},
            "nodes": [{"label": "读资料", "detail": "先读取可定位的公开原文", "icon": "book", "claim_ids": [primary]},
                      {"label": "核来源", "detail": "每条事实都能找到原句", "icon": "search", "claim_ids": [primary]},
                      {"label": "留边界", "detail": "未核实处标出待人工补充", "icon": "check", "claim_ids": [primary]}]},
        "explainer": _explainer_sections(answer, ids), "learning_check": {
            "question": "为什么这一版作品还需要人工核对？",
            "answer": "因为初稿由本地模板和初步解释整理，尚未由模型审核、也没有专家终审，结论需对照来源确认。",
            "claim_ids": [primary]},
    })
    return draft, "千问规划与一次结构修复均未通过，改用本地确定性6镜模板（内容待人工核实）"


def _explainer_sections(primer_answer, claim_ids):
    """Three distinct sections; primer answer is verbatim and explicitly unverified."""
    text = (primer_answer or "").strip()
    parts = []
    if len(text) >= 150:
        size = len(text) // 3
        parts = [text[:size], text[size:size * 2], text[size * 2:]]
    elif text:
        parts = [text]
    suffix = "（本段来自千问初步解释，标注未核实，尚未对照来源定稿）"
    sections = []
    for index, part in enumerate(parts, 1):
        body = part + suffix if len(part) < 50 else part
        sections.append({"heading": f"初步解释{index}（未核实）", "body": _cut(body, 220), "claim_ids": claim_ids[:1]})
    fillers = ["先把问题拆成容易查的小问题，再逐项核对资料，把每一步都写清机制和例子。",
               "把每个机制用自己的话讲一遍，再对照原文检查，例子和边界各占一节，避免自相矛盾。",
               "最后留出边界：资料之外不要下结论，影响和局限也要说明清楚，别把推测当成事实。"]
    while len(sections) < 3:
        role_text = fillers[len(sections) % 3]
        sections.append({"heading": f"整理说明{len(sections) + 1}", "body": role_text + suffix, "claim_ids": claim_ids[:1]})
    return sections[:3]


_ROLE_ICONS = {"hook": "question", "example": "person", "mechanism": "server", "process": "book",
               "misconception": "question", "boundary": "lock", "takeaway": "check"}

_VISUAL_KEYWORDS = [
    (("太阳",), "sun", "太阳", "提供光照"), (("月亮", "月球"), "moon", "月亮", "反射太阳光"),
    (("地球",), "earth", "地球", "观察月亮亮面"), (("AI", "模型", "人工智能"), "robot", "AI", "生成语言或判断"),
    (("API", "接口"), "book", "API规则", "规定软件怎样沟通"), (("手机", "应用", "App"), "phone", "应用", "发出功能请求"),
    (("服务器", "后台", "系统"), "server", "后台系统", "接收并处理请求"), (("学生", "学习", "复习"), "person", "学习者", "主动理解与回想"),
    (("资料", "原文", "来源"), "book", "权威资料", "提供可核对依据"), (("检查", "核对", "验证"), "check", "核查", "确认事实与边界"),
    (("安全", "权限", "隐私"), "lock", "安全边界", "需要额外保护"), (("云",), "cloud", "云服务", "通过网络提供能力"),
]


def _fallback_actors(scene):
    text = scene.heading + scene.narration + scene.visual_action
    actors, icons = [], set()
    for words, icon, label, explanation in _VISUAL_KEYWORDS:
        if icon not in icons and any(word in text for word in words):
            actors.append({"icon": icon, "label": label, "explanation": explanation})
            icons.add(icon)
        if len(actors) == 4:
            break
    if len(actors) < 2:
        fallback = _ROLE_ICONS.get(scene.role or "", "question")
        for icon, label, explanation in ((fallback, scene.heading[:12], "展示本镜核心概念"),
                                         ("person", "公众", "理解这部分知识"),
                                         ("book", "资料", "提供可核对依据")):
            if icon not in icons:
                actors.append({"icon": icon, "label": label, "explanation": explanation})
                icons.add(icon)
            if len(actors) >= 2:
                break
    return actors


def deterministic_cartoon_plan(draft):
    """Deterministic object plan when Qwen cartoon planning fails; text stays from the draft."""
    from app.services.studio_cartoon import CartoonPlan
    scenes = []
    for scene in draft.scenes:
        actors = _fallback_actors(scene)
        labels = "、".join(actor["label"] for actor in actors)
        scenes.append({"scene_id": scene.scene_id, "relationship": "reveal",
                       "caption": _cut(f"{scene.heading}：用{labels}帮助理解", 42) + "（模板）",
                       "actors": actors})
    return CartoonPlan.model_validate({"scenes": scenes})
