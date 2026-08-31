"""Code-native, editable diagrams. No generated bitmap or stock artwork is used."""
from html import escape
import io
import json
import zipfile

from app.studio_models import StudioDraft
from app.services.studio_pipeline import presentation


def lines(text, width):
    return [text[i:i + width] for i in range(0, len(text), width)] or [""]


def svg_text(text, x, y, size=24, width=42, color="#d3e6e8"):
    return "".join(f'<text x="{x}" y="{y + i * (size + 12)}" font-size="{size}" fill="{color}">{escape(line)}</text>'
                   for i, line in enumerate(lines(text, width)))


def poster_svg(project, version=None):
    v = version or project["versions"][-1]
    draft = StudioDraft.model_validate(v["draft"])
    mock = v["mode"] == "mock"
    status = "MOCK · 流程占位，不可提交" if mock else "AI生成草稿 · 待科学与视觉终审"
    parts = [svg_text("SCIVIS / 科学可视化工作台", 64, 64, 18),
             svg_text(draft.title, 64, 140, 42, 25, "#fff7df"),
             svg_text(draft.takeaway, 64, 202, 25, 40),
             '<rect x="56" y="306" width="1088" height="260" rx="28" fill="#153d48"/>',
             svg_text("01 / 看懂关键关系", 82, 350, 18, color="#ffd378")]
    labels = draft.diagram.labels
    stride = 1020 / len(labels)
    for i, label in enumerate(labels):
        x = 86 + i * stride
        parts.append(f'<rect x="{x}" y="388" width="{stride - 30}" height="86" rx="22" fill="#245666" stroke="#65cabd"/>')
        parts.append(svg_text(label, x + 18, 422, 22, max(5, int((stride - 68) / 22)), "#ffffff"))
        if i < len(labels) - 1 and draft.diagram.kind != "comparison":
            parts.append(svg_text("→", x + stride - 26, 440, 24, color="#ffd378"))
    if draft.diagram.kind == "cycle":
        parts.append('<path d="M1050 480 V499 H158 V480" fill="none" stroke="#65cabd" stroke-dasharray="7 5"/>')
    parts.append(svg_text("概念示意 · " + draft.diagram.caption, 82, 526, 18, 54))
    y = 604
    for i, claim in enumerate(draft.claims):
        claim_lines = len(lines(claim.text, 41))
        caveat_lines = len(lines("边界：" + claim.boundary, 47))
        height = 72 + claim_lines * 36 + caveat_lines * 32
        parts += [f'<rect x="56" y="{y}" width="1088" height="{height}" rx="26" fill="#133540"/>',
                  f'<circle cx="106" cy="{y + 54}" r="25" fill="#ffd378"/>',
                  svg_text(str(i + 1), 99, y + 63, 24, color="#143540"),
                  svg_text(claim.text, 158, y + 48, 24, 41, "#ffffff"),
                  svg_text("边界：" + claim.boundary, 158, y + 62 + claim_lines * 36, 20, 47),
                  svg_text(f"{claim.claim_id} · 来源 {claim.source_id}", 158, y + height - 15, 15, color="#76cfc2")]
        y += height + 20
    parts.append(svg_text(status + f" · v{v['version']}", 64, y + 30, 18, 60, "#ffd378"))
    for source in project["input"]["sources"]:
        y += 34
        parts.append(svg_text(f"{source['source_id']} {source['title']}", 64, y + 36, 17, 62))
        y += (len(lines(f"{source['source_id']} {source['title']}", 62)) - 1) * 29
    height = y + 95
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">'
            '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}</style>'
            f'<rect width="1200" height="{height}" fill="#08252f"/>' + "".join(parts) + '</svg>')


def srt_time(seconds):
    millis = round(seconds * 1000)
    return f"{millis // 3600000:02}:{millis // 60000 % 60:02}:{millis // 1000 % 60:02},{millis % 1000:03}"


def export_zip(project):
    version = project["versions"][-1]
    draft = StudioDraft.model_validate(version["draft"])
    timing = presentation(draft)
    subtitles, start, index = [], 0, 1
    for scene in timing:
        duration = scene["estimated_seconds"] / len(scene["subtitles"])
        for subtitle in scene["subtitles"]:
            subtitles.append(f"{index}\n{srt_time(start)} --> {srt_time(start + duration)}\n{subtitle}\n")
            start += duration
            index += 1
    sections = "".join(f'<section><h2>{escape(s.heading)}</h2><p>{escape(s.narration)}</p><p>画面：{escape(s.visual_action)}</p><small>证据：{escape(", ".join(s.claim_ids))}</small></section>' for s in draft.scenes)
    html = ('<!doctype html><html lang="zh"><meta charset="utf-8"><title>科普作品交接</title>'
            '<style>body{font:20px/1.8 sans-serif;max-width:960px;margin:40px auto;padding:24px;background:#eef5f1;color:#12343e}img{width:100%;max-width:600px}section{background:white;padding:24px;margin:20px 0;border-radius:16px}</style>'
            f'<h1>{escape(draft.title)}</h1><p>AI生成草稿，待人工终审。字幕时间为估算，尚未合成通用视频或配音。</p><img src="poster.svg" alt="海报">{sections}</html>')
    files = {"poster.svg": poster_svg(project), "index.html": html,
             "project.json": json.dumps(project, ensure_ascii=False, indent=2),
             "storyboard.json": draft.model_dump_json(indent=2),
             "subtitles-estimated.srt": "\n".join(subtitles),
             "README.txt": "本包含用户提供的资料摘录和AI草稿，分享前请检查资料授权及个人信息。\nSVG为程序化可编辑概念图，不是Qwen-Image图片。\n分镜为千问独立编写（Mock例外），SRT时长为估算；本包不含自动生成的MP4或配音。\n引文定位不等于科学正确，AI审核不等于专家终审；不可直接把草稿作为已验收参赛成品。\n"}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return buffer.getvalue()
