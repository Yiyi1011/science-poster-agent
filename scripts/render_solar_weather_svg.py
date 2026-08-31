from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "artifacts" / "solar-weather-poster-plan-v1.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "solar-weather-poster-v2.svg"


def wrap_cn(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= width and char not in "，。；：、）】”’":
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines


def text_block(
    x: int,
    y: int,
    text: str,
    width: int,
    font_size: int,
    line_height: int,
    fill: str,
    weight: int = 400,
    opacity: float = 1,
) -> str:
    lines = wrap_cn(text, width)
    tspans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return (
        f'<text x="{x}" y="{y}" font-size="{font_size}" font-weight="{weight}" '
        f'fill="{fill}" opacity="{opacity}">{tspans}</text>'
    )


def main() -> None:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    cards = plan["fact_cards"]
    colors = ["#9B7BFF", "#FF9B52", "#54D8E8"]
    timings = ["约 8 分钟", "几十分钟—数小时", "约 18 小时—数天"]
    labels = ["电磁辐射", "太阳高能粒子", "日冕物质抛射"]
    signals = ["LIGHT", "PARTICLES", "PLASMA + FIELD"]
    svg: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#061224"/><stop offset="0.58" stop-color="#0A1D38"/><stop offset="1" stop-color="#07101E"/></linearGradient>',
        '<radialGradient id="sun"><stop stop-color="#FFF4A8"/><stop offset="0.45" stop-color="#FFB24E"/><stop offset="1" stop-color="#FF5C3D"/></radialGradient>',
        '<radialGradient id="earth"><stop stop-color="#7EE8FF"/><stop offset="0.45" stop-color="#2478C9"/><stop offset="1" stop-color="#103B74"/></radialGradient>',
        '<filter id="glow"><feGaussianBlur stdDeviation="8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        '<marker id="arrow-purple" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="#9B7BFF"/></marker>',
        '<marker id="arrow-orange" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="#FF9B52"/></marker>',
        '<marker id="arrow-cyan" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="#54D8E8"/></marker>',
        '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif} .mono{font-family:Consolas,"SFMono-Regular",monospace}</style>',
        "</defs>",
        '<rect width="1200" height="1600" fill="url(#bg)"/>',
        '<circle cx="1050" cy="80" r="280" fill="#153D66" opacity=".15"/>',
        '<circle cx="90" cy="1490" r="250" fill="#4D2D75" opacity=".13"/>',
        '<path d="M0 290 C260 250 390 320 620 285 S990 235 1200 275" fill="none" stroke="#86B7D8" stroke-opacity=".12"/>',
        '<text x="64" y="66" font-size="17" font-weight="700" letter-spacing="1.5" fill="#78D9F2">跨主题科普视觉智能体 · 临时版</text>',
        '<rect x="1010" y="42" width="126" height="34" rx="17" fill="#143450" stroke="#5A8AA8" stroke-opacity=".55"/>',
        '<text x="1073" y="65" text-anchor="middle" font-size="14" font-weight="700" fill="#C5E8F4">面向公众</text>',
        f'<text x="64" y="150" font-size="58" font-weight="760" letter-spacing="1" fill="#F6FBFF">{escape(plan["title"])}</text>',
        f'<text x="66" y="207" font-size="30" font-weight="500" fill="#BBD4E6">{escape(plan["subtitle"])}</text>',
        '<text x="66" y="252" font-size="18" fill="#7394AD">一次太阳爆发，三类信使并不同步抵达，也不会自动形成灾害链。</text>',
        '<rect x="54" y="302" width="1092" height="490" rx="32" fill="#0B2039" stroke="#3C6683" stroke-opacity=".55"/>',
        '<text x="82" y="345" class="mono" font-size="15" letter-spacing="2" fill="#7D9EB6">ONE EVENT · THREE MESSENGERS</text>',
        '<line x1="82" y1="370" x2="1118" y2="370" stroke="#54738A" stroke-opacity=".35"/>',
        '<circle cx="142" cy="557" r="82" fill="#FF7A3D" opacity=".14" filter="url(#glow)"/>',
        '<circle cx="142" cy="557" r="58" fill="url(#sun)" filter="url(#glow)"/>',
        '<path d="M142 475 v-28 M142 667 v-28 M60 557 H32 M252 557 h-28 M84 499 l-20-20 M220 635 l-20-20 M84 615 l-20 20 M220 479 l-20 20" stroke="#FFB754" stroke-width="7" stroke-linecap="round" opacity=".8"/>',
        '<text x="142" y="680" text-anchor="middle" font-size="18" font-weight="700" fill="#FFE0B2">太阳活动区</text>',
        '<circle cx="1050" cy="557" r="65" fill="#52C9F3" opacity=".13" filter="url(#glow)"/>',
        '<circle cx="1050" cy="557" r="45" fill="url(#earth)"/>',
        '<path d="M1018 542 q20-30 43-13 q22 15 30-3 M1017 574 q25-10 37 7 q18 14 35-2" fill="none" stroke="#8EEBBE" stroke-width="9" stroke-linecap="round" opacity=".85"/>',
        '<path d="M1095 491 q68 66 0 132" fill="none" stroke="#75D9F4" stroke-width="2" opacity=".4"/>',
        '<text x="1050" y="680" text-anchor="middle" font-size="18" font-weight="700" fill="#C4F2FF">地球附近</text>',
        '<path d="M230 435 C480 392 720 402 966 480" fill="none" stroke="#9B7BFF" stroke-width="7" stroke-linecap="round" marker-end="url(#arrow-purple)" filter="url(#glow)"/>',
        '<path d="M230 550 C460 515 720 520 968 545" fill="none" stroke="#FF9B52" stroke-width="5" stroke-linecap="round" stroke-dasharray="3 18" marker-end="url(#arrow-orange)"/>',
        '<path d="M230 655 C480 720 750 700 968 620" fill="none" stroke="#54D8E8" stroke-width="16" stroke-linecap="round" stroke-opacity=".25"/>',
        '<path d="M230 655 C480 720 750 700 968 620" fill="none" stroke="#54D8E8" stroke-width="5" stroke-linecap="round" marker-end="url(#arrow-cyan)"/>',
    ]

    lane_y = [410, 525, 640]
    for index, (timing, label, signal, color) in enumerate(zip(timings, labels, signals, colors)):
        y = lane_y[index]
        svg.extend(
            [
                f'<rect x="405" y="{y}" width="390" height="68" rx="16" fill="#071528" fill-opacity=".92" stroke="{color}" stroke-opacity=".55"/>',
                f'<text x="430" y="{y + 28}" class="mono" font-size="15" font-weight="700" fill="{color}" letter-spacing="1.2">0{index + 1} · {signal}</text>',
                f'<text x="430" y="{y + 54}" font-size="21" font-weight="700" fill="#F5FAFD">{label}</text>',
                f'<text x="770" y="{y + 43}" text-anchor="end" font-size="22" font-weight="760" fill="{color}">{timing}</text>',
            ]
        )

    card_x = [54, 417, 780]
    for index, card in enumerate(cards):
        x = card_x[index]
        color = colors[index]
        svg.extend(
            [
                f'<rect x="{x}" y="828" width="348" height="572" rx="26" fill="#0C2139" stroke="{color}" stroke-opacity=".48"/>',
                f'<rect x="{x}" y="828" width="348" height="9" rx="4" fill="{color}"/>',
                f'<text x="{x + 24}" y="880" class="mono" font-size="16" font-weight="700" letter-spacing="1.5" fill="{color}">0{index + 1} / {signals[index]}</text>',
                f'<text x="{x + 24}" y="930" font-size="31" font-weight="760" fill="#F4FAFD">{timings[index]}</text>',
                f'<text x="{x + 24}" y="970" font-size="20" font-weight="700" fill="{color}">{labels[index]}</text>',
                text_block(x + 24, 1017, card["claim"], 14, 18, 31, "#E7F2F8", 500),
                f'<line x1="{x + 24}" y1="1198" x2="{x + 324}" y2="1198" stroke="#668198" stroke-opacity=".35"/>',
                f'<text x="{x + 24}" y="1230" font-size="16" font-weight="700" letter-spacing="1" fill="{color}">条件与边界</text>',
                text_block(x + 24, 1267, card["caveat"], 16, 17, 28, "#B7CEDB", 400),
            ]
        )

    svg.extend(
        [
            '<rect x="54" y="1420" width="1092" height="140" rx="22" fill="#08192C" stroke="#4E7893" stroke-opacity=".8"/>',
            '<rect x="68" y="1435" width="742" height="42" rx="12" fill="#48271F" stroke="#FF9B52"/>',
            '<text x="88" y="1463" font-size="20" font-weight="760" fill="#FFD8BC">重要边界：强耀斑 ≠ 必然伴随 CME ≠ 必然形成强地磁暴</text>',
            '<text x="78" y="1510" font-size="17" font-weight="700" fill="#E2F1F7">来源：NOAA / ESA / 中国科学院国家天文台 · 事实卡 S-SW-001—005</text>',
            '<text x="78" y="1543" font-size="17" fill="#BFD6E2">科普用途，不替代实时空间天气预报；事件判断应以官方监测为准。</text>',
            '<text x="1122" y="1510" text-anchor="end" class="mono" font-size="14" font-weight="700" fill="#9FC0D1">RAG ≥ 0.50</text>',
            '<text x="1122" y="1542" text-anchor="end" font-size="14" font-weight="700" fill="#9FC0D1">QWEN · 人工复核</text>',
            "</svg>",
        ]
    )
    OUTPUT_PATH.write_text("".join(svg), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
