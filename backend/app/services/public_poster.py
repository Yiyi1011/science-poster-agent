"""Public-first SVG layout, with evidence retained outside the main reading path.

Icons are code-native conceptual symbols, never scientific measurements or AI bitmaps.
"""
from html import escape
import re
import unicodedata


def units(text):
    return sum(1 if unicodedata.east_asian_width(c) in "WF" else .58 for c in text)


def wrap(text, width):
    # Keep normal Latin terms whole and measure them differently from CJK glyphs.
    result, line = [], ""
    for token in re.findall(r"[A-Za-z0-9]+(?:[-’'][A-Za-z0-9]+)*|.", text):
        if line and units(line + token) > width:
            result.append(line)
            line = ""
        line += token
    return result + [line] if line else result or [""]


def text(value, x, y, size=28, width=32, color="#f6f4e9", weight=400):
    return "".join(f'<text x="{x}" y="{y + i * (size + 12)}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(line)}</text>'
                   for i, line in enumerate(wrap(value, width)))


def icon(name, x, y, scale=1):
    shapes = {
        "chat": '<path d="M10 12h56v36H36L20 61V48H10z"/><path d="M23 24h30M23 35h20"/>',
        "book": '<path d="M38 16Q22 6 7 14v43q15-8 31 2 16-10 31-2V14q-15-8-31 2v43"/><path d="M17 25l12 2M47 27l12-2"/>',
        "search": '<circle cx="31" cy="29" r="21"/><path d="M47 45l20 20M22 29h18M31 20v18"/>',
        "check": '<rect x="10" y="8" width="54" height="58" rx="10"/><path d="M22 36l10 10 23-24"/>',
        "clock": '<circle cx="38" cy="36" r="29"/><path d="M38 16v22l16 10"/>',
        "spark": '<path d="M42 6L15 40h22l-5 26 28-36H39z"/>',
        "question": '<circle cx="38" cy="36" r="29"/><path d="M27 25q0-15 20-8 14 9-6 18l-3 8M38 52v2"/>',
    }
    return f'<g transform="translate({x} {y}) scale({scale})" fill="none" stroke="#75d9c4" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">{shapes[name]}</g>'


def render(project, version, draft):
    public = draft.public_poster
    parts = [text("SCIVIS   /   把知识讲明白", 64, 64, 18, color="#75d9c4"),
             text(draft.title, 64, 150, 52, 20, weight=700)]
    # Reserve breathing room after the final title baseline, also for wrapped titles.
    y = 150 + len(wrap(draft.title, 20)) * 64 + 24
    parts.append(text(draft.takeaway, 64, y, 28, 37, color="#ffd782"))
    y += len(wrap(draft.takeaway, 37)) * 40 + 30
    # Everyday entry point before any terminology or mechanism.
    example_height = 100 + len(wrap(public.example.body, 33)) * 40
    parts += [f'<rect x="56" y="{y}" width="1088" height="{example_height}" rx="28" fill="#193e49"/>',
              icon("question", 78, y + 35), text(public.example.heading, 174, y + 43, 22, color="#75d9c4", weight=700),
              text(public.example.body, 174, y + 89, 28, 33)]
    y += example_height + 42
    parts.append(text("看图理解", 64, y, 22, color="#75d9c4"))
    y += 28
    count = len(public.nodes)
    # 4 nodes use a 2x2 grid; all panels have meaningful body text and a symbol.
    cols = 2 if count == 4 else count
    stride = 1080 / cols
    rows = 2 if count == 4 else 1
    detail_width = max(8, int((stride - 66) / 26))
    node_height = 172 + max(len(wrap(n.detail, detail_width)) for n in public.nodes) * 38
    for i, node in enumerate(public.nodes):
        nx, ny = 60 + (i % cols) * stride, y + (i // cols) * (node_height + 26)
        parts += [f'<rect x="{nx}" y="{ny}" width="{stride - 22}" height="{node_height}" rx="24" fill="#204955"/>',
                  icon(node.icon, nx + 24, ny + 20), text(f"0{i + 1}", nx + stride - 90, ny + 51, 22, color="#75d9c4"),
                  text(node.label, nx + 24, ny + 120, 28, detail_width, weight=700),
                  text(node.detail, nx + 24, ny + 171, 26, detail_width)]
        if draft.diagram.kind != "comparison" and i < count - 1:
            if (i + 1) % cols:
                parts.append(text("→", nx + stride - 25, ny + 90, 26, color="#ffd782"))
            else:
                # Reading order continues at the start of the next row, never a false diagonal link.
                parts.append(text("↓ 继续下一行", 68, ny + node_height + 22, 16, color="#ffd782"))
    y += rows * (node_height + 26)
    prefix = "循环示意 · 末步回到第一步：" if draft.diagram.kind == "cycle" else "理解示意 · "
    caption = prefix + draft.diagram.caption
    parts.append(text(caption, 66, y + 5, 20, 51, color="#a4c9cd"))
    y += len(wrap(caption, 51)) * 32 + 34
    # Short public copy, no quotations or academic caveat paragraphs in the reading path.
    for i, card in enumerate(public.cards):
        height = 104 + len(wrap(card.body, 32)) * 40
        parts += [f'<rect x="56" y="{y}" width="1088" height="{height}" rx="24" fill="#123641"/>',
                  f'<circle cx="104" cy="{y + 49}" r="25" fill="#ffd782"/>',
                  text(str(i + 1), 96, y + 58, 24, color="#123641"),
                  text(card.heading, 160, y + 47, 30, weight=700), text(card.body, 160, y + 94, 28, 32),
                  text("依据 " + " · ".join(card.claim_ids), 160, y + height - 15, 15, color="#75d9c4")]
        y += height + 18
    y += 28
    parts += [text(public.caution.heading, 64, y, 24, color="#ffd782", weight=700),
              text(public.caution.body, 64, y + 43, 26, 40, color="#c5dfe0")]
    y += 43 + len(wrap(public.caution.body, 40)) * 38 + 34
    status = "功能演示" if version["mode"] == "mock" else "来源可核对 · 修改有记录"
    parts.append(text(status + f"  /  v{version['version']}", 64, y, 18, 58, "#ffd782"))
    y += 34
    sources = project["input"]["sources"] or (project.get("research") or {}).get("sources", [])
    by_id = {s["source_id"]: s for s in sources}
    for claim in draft.claims:
        source = by_id.get(claim.source_id, {})
        label = f"{claim.claim_id} → {claim.source_id}  {source.get('title', '来源见证据页')}"
        parts.append(text(label, 64, y, 15, 112, "#a4c9cd"))
        y += len(wrap(label, 112)) * 27
    parts.append(text("完整引文、适用条件与修改记录保存在证据页及导出包。", 64, y + 8, 15, 112, "#a4c9cd"))
    height = y + 75
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">'
            '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}</style>'
            f'<rect width="1200" height="{height}" fill="#08252f"/>' + "".join(parts) + '</svg>')
