from __future__ import annotations

import asyncio
import json
import re
import sys
import wave
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKFLOW_ROOT = PROJECT_ROOT / "artifacts" / "workflow"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "video" / "solar-weather-v001"

sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.models import VideoScene, VideoStoryboard  # noqa: E402
from app.services.qwen_tts_client import QwenTtsClient  # noqa: E402
from app.services.usage_ledger import recorded_tts_cost  # noqa: E402
from app.services.visual_workflow import persist_version  # noqa: E402


def srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。；！？])", text) if part.strip()]


def concatenate_wav(paths: list[Path], output_path: Path) -> float:
    parameters = None
    frames: list[bytes] = []
    total_frames = 0
    frame_rate = 0
    for path in paths:
        with wave.open(str(path), "rb") as audio:
            current = audio.getparams()
            signature = (current.nchannels, current.sampwidth, current.framerate, current.comptype)
            if parameters is None:
                parameters = current
                expected = signature
                frame_rate = current.framerate
            elif signature != expected:
                raise RuntimeError("TTS clips use incompatible WAV formats.")
            chunk = audio.readframes(current.nframes)
            frames.append(chunk)
            total_frames += len(chunk) // (current.nchannels * current.sampwidth)
    if parameters is None:
        raise RuntimeError("No WAV clips were generated.")
    with wave.open(str(output_path), "wb") as output:
        output.setparams(parameters)
        for chunk in frames:
            output.writeframes(chunk)
    return total_frames / frame_rate


def write_actual_srt(storyboard: VideoStoryboard, durations: list[float]) -> Path:
    blocks: list[str] = []
    index = 1
    scene_start = 0.0
    for scene, duration in zip(storyboard.scenes, durations, strict=True):
        scene_clauses = clauses(scene.subtitle) or [scene.subtitle]
        weights = [max(1, len(item)) for item in scene_clauses]
        total = sum(weights)
        cursor = scene_start
        for clause, weight in zip(scene_clauses, weights, strict=True):
            end = cursor + duration * weight / total
            blocks.append(f"{index}\n{srt_time(cursor)} --> {srt_time(end)}\n{clause}\n")
            index += 1
            cursor = end
        scene_start += duration
    path = OUTPUT_ROOT / "subtitles-actual-v002.srt"
    path.write_text("\n".join(blocks), encoding="utf-8-sig")
    return path


async def main() -> None:
    storyboard_path = sorted(
        WORKFLOW_ROOT.glob("*/video-storyboard-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[0]
    envelope = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard = VideoStoryboard.model_validate(envelope["payload"])
    output_dir = OUTPUT_ROOT / "audio-clips"
    before_cost = recorded_tts_cost()
    client = QwenTtsClient(settings)
    results = []
    for scene in storyboard.scenes:
        results.append(await client.generate(VideoScene.model_validate(scene), output_dir))

    clip_paths = [PROJECT_ROOT / result.file_path for result in results]
    combined_path = OUTPUT_ROOT / "narration-combined-v001.wav"
    total_duration = concatenate_wav(clip_paths, combined_path)
    srt_path = write_actual_srt(storyboard, [result.duration_seconds for result in results])
    package_manifest = persist_version(
        storyboard.task_id,
        "audio-package",
        {
            "model": settings.qwen_tts_model,
            "voice": settings.qwen_tts_voice,
            "clips": [result.model_dump() for result in results],
            "combined_file": str(combined_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "subtitle_file": str(srt_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "actual_duration_seconds": round(total_duration, 3),
            "human_science_review_required": True,
        },
    )
    print(
        json.dumps(
            {
                "status": "needs_human_listening_review",
                "model": settings.qwen_tts_model,
                "clips": len(results),
                "combined_file": str(combined_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "actual_duration_seconds": round(total_duration, 3),
                "estimated_tts_cost_before_cny": before_cost,
                "estimated_tts_cost_after_cny": recorded_tts_cost(),
                "tts_sub_budget_cny": settings.tts_budget_cny,
                "package_manifest": package_manifest,
                "secret_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
