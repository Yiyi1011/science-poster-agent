from __future__ import annotations

from html import escape

from app.models import PosterPlan


COLORS = ("#9B7BFF", "#FF9B52", "#54D8E8")


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        current += character
        if len(current) >= width and character not in "，。；：、）】”’":
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines


def _text_block(x: int, y: int, text: str, width: int, size: int, line: int) -> str:
    tspans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line}">{escape(value)}</tspan>'
        for index, value in enumerate(_wrap(text, width))
    )
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="#DDEBF3">{tspans}</text>'


def _card_heading(text: str, fallback: str) -> str:
    heading = text.split("：", 1)[0].strip().rstrip("。！？")
    if not heading:
        return fallback
    return heading if len(heading) <= 13 else f"{heading[:12]}…"


def render_poster_svg(plan: PosterPlan) -> str:
    cards = plan.fact_cards[:3]
    while len(cards) < 3:
        cards.append(
            type(plan.fact_cards[0])(
                claim_id=f"missing-{len(cards)}",
                claim="当前资料不足，等待补充权威证据。",
                evidence_status="missing",
                caveat="证据不足时不生成确定性科学结论。",
            )
            if plan.fact_cards
            else None
        )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600">',
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#061224"/><stop offset="1" stop-color="#0B2039"/></linearGradient>',
        '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif}</style></defs>',
        '<rect width="1200" height="1600" fill="url(#bg)"/>',
        '<circle cx="1060" cy="90" r="280" fill="#174066" opacity=".18"/>',
        '<text x="64" y="68" font-size="17" letter-spacing="2" fill="#72D6EC">跨主题科普视觉智能体 · 临时版</text>',
        f'<text x="64" y="160" font-size="54" font-weight="760" fill="#F5FAFD">{escape(plan.title)}</text>',
        f'<text x="66" y="215" font-size="28" fill="#B9D4E6">{escape(plan.subtitle)}</text>',
        '<rect x="54" y="285" width="1092" height="410" rx="30" fill="#0A1D34" stroke="#365C78"/>',
        '<text x="82" y="330" font-size="14" letter-spacing="2" fill="#7899B0">VISUAL NARRATIVE / 科学叙事结构</text>',
    ]
    for index, section in enumerate(plan.sections[:3]):
        y = 375 + index * 98
        color = COLORS[index]
        parts.extend(
            [
                f'<circle cx="103" cy="{y}" r="22" fill="{color}"/>',
                f'<text x="103" y="{y + 7}" text-anchor="middle" font-size="17" font-weight="700" fill="#071224">{index + 1}</text>',
                f'<text x="145" y="{y - 2}" font-size="22" font-weight="700" fill="#F3F9FC">{escape(section.heading)}</text>',
                f'<text x="145" y="{y + 28}" font-size="16" fill="#9EB8C9">{escape(section.content_summary[:52])}</text>',
            ]
        )
    evidence_route = (
        "EVIDENCE ROUTE · 权威资料直接输入"
        if plan.retrieval_status == "user_sources"
        else f"RAG {plan.retrieval_status} · MAX SCORE {plan.retrieval_max_score or 0:.3f}"
    )
    parts.append(
        f'<text x="82" y="657" font-size="15" fill="#6ED5E8">{escape(evidence_route)}</text>'
    )
    for index, card in enumerate(cards):
        x = 54 + index * 363
        color = COLORS[index]
        if card is None:
            continue
        timing = _card_heading(card.claim, f"事实 {index + 1}")
        parts.extend(
            [
                f'<rect x="{x}" y="740" width="348" height="650" rx="26" fill="#0C2139" stroke="{color}"/>',
                f'<rect x="{x}" y="740" width="348" height="9" rx="4" fill="{color}"/>',
                f'<text x="{x + 24}" y="800" font-size="16" font-weight="700" letter-spacing="1.5" fill="{color}">事实卡 0{index + 1}</text>',
                f'<text x="{x + 24}" y="852" font-size="23" font-weight="760" fill="#F5FAFD">{escape(timing)}</text>',
                _text_block(x + 24, 910, card.claim, 14, 18, 31),
                f'<line x1="{x + 24}" y1="1125" x2="{x + 324}" y2="1125" stroke="#59758A" opacity=".5"/>',
                f'<text x="{x + 24}" y="1170" font-size="15" font-weight="700" letter-spacing="1.2" fill="{color}">条件与边界</text>',
                _text_block(x + 24, 1212, card.caveat, 16, 17, 29),
                f'<text x="{x + 24}" y="1350" font-size="14" font-weight="700" fill="#8FB2C6">{escape(card.evidence_status.upper())}</text>',
            ]
        )
    source_ids = list(
        dict.fromkeys(
            evidence.source_id
            for card in plan.fact_cards
            for evidence in card.evidence
            if evidence.source_id
        )
    )
    sources = " · ".join(plan.source_documents or source_ids) or "用户提供的审核资料"
    boundary = next(
        (card.caveat.strip() for card in plan.fact_cards if card.caveat.strip()),
        plan.safety_note.strip() or "结论仅适用于已提供证据的范围。",
    )
    parts.extend(
        [
            '<rect x="54" y="1405" width="1092" height="48" rx="14" fill="#44251F" stroke="#FF9B52"/>',
            f'<text x="78" y="1437" font-size="20" font-weight="760" fill="#FFD8BC">重要边界：{escape(boundary[:49])}</text>',
            '<rect x="54" y="1468" width="1092" height="96" rx="20" fill="#08182A" stroke="#4E7893"/>',
            '<text x="78" y="1500" font-size="16" font-weight="700" letter-spacing="1.5" fill="#6ED5E8">来源可追溯 · 生成内容已进入人工科学审核</text>',
            f'<text x="78" y="1532" font-size="18" fill="#E6F2F8">来源：{escape(sources[:64])}</text>',
            f'<text x="78" y="1556" font-size="16" fill="#BFD5E1">{escape(sources[64:128])}</text>',
            '<text x="1122" y="1500" text-anchor="end" font-size="14" font-weight="700" fill="#A9C4D2">QWEN · 证据约束 · 人工复核</text>',
            "</svg>",
        ]
    )
    return "".join(parts)
