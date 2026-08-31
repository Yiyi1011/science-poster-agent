from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = PROJECT_ROOT / "artifacts" / "workflow"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "video" / "solar-weather-v001"


def srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def clauses(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[。；！？])", text) if part.strip()]
    return parts or [text.strip()]


def main() -> None:
    source_path = sorted(
        WORKFLOW_ROOT.glob("*/video-storyboard-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[0]
    envelope = json.loads(source_path.read_text(encoding="utf-8"))
    storyboard = envelope["payload"]
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    narration_lines = [
        f"# {storyboard['title']}｜60秒AI旁白审核稿",
        "",
        "> 声音方案：普通话中性AI音色＋同步字幕。正式合成前必须人工确认科学事实和读音。",
        "",
    ]
    source_map: list[dict] = []
    srt_blocks: list[str] = []
    subtitle_index = 1
    scene_start = 0.0
    for scene in storyboard["scenes"]:
        narration_lines.extend(
            [
                f"## {scene['heading']}（{scene['duration_seconds']}秒）",
                "",
                scene["narration"],
                "",
                f"- 事实卡：{', '.join(scene['source_claim_ids'])}",
                f"- 分镜ID：`{scene['scene_id']}`",
                "",
            ]
        )
        scene_clauses = clauses(scene["subtitle"])
        weights = [max(1, len(item)) for item in scene_clauses]
        total_weight = sum(weights)
        cursor = scene_start
        for clause, weight in zip(scene_clauses, weights, strict=True):
            allocated = scene["duration_seconds"] * weight / total_weight
            end = cursor + allocated
            srt_blocks.append(
                f"{subtitle_index}\n{srt_time(cursor)} --> {srt_time(end)}\n{clause}\n"
            )
            subtitle_index += 1
            cursor = end
        source_map.append(
            {
                "scene_id": scene["scene_id"],
                "heading": scene["heading"],
                "start_seconds": scene_start,
                "end_seconds": scene_start + scene["duration_seconds"],
                "source_claim_ids": scene["source_claim_ids"],
                "status": "awaiting_human_science_review",
            }
        )
        scene_start += scene["duration_seconds"]

    (OUTPUT_ROOT / "narration-review-v001.md").write_text(
        "\n".join(narration_lines), encoding="utf-8"
    )
    (OUTPUT_ROOT / "subtitles-v001.srt").write_text(
        "\n".join(srt_blocks), encoding="utf-8-sig"
    )
    (OUTPUT_ROOT / "source-map-v001.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_ROOT / "voice-config-v001.json").write_text(
        json.dumps(
            {
                "provider": "Alibaba Cloud Model Studio",
                "model": "pending_availability_check",
                "language": "zh-CN",
                "voice_style": "neutral_science_explainer",
                "speech_rate": 0.95,
                "narration_mode": storyboard["narration_mode"],
                "status": "planned_not_called",
                "paid_model_called": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_dir": str(OUTPUT_ROOT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "duration_seconds": storyboard["total_duration_seconds"],
                "subtitle_blocks": len(srt_blocks),
                "source_mapped_scenes": len(source_map),
                "paid_model_called": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
