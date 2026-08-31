from __future__ import annotations

import json
import sys
import wave
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKFLOW_ROOT = PROJECT_ROOT / "artifacts" / "workflow"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "video" / "solar-weather-v001"

sys.path.insert(0, str(BACKEND_ROOT))

from app.models import TtsGenerationResult, VideoStoryboard  # noqa: E402
from app.services.qwen_tts_client import wav_duration  # noqa: E402
from app.services.visual_workflow import persist_version  # noqa: E402

from synthesize_video_narration import concatenate_wav, write_actual_srt  # noqa: E402


def main() -> None:
    storyboard_path = sorted(
        WORKFLOW_ROOT.glob("*/video-storyboard-v*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[0]
    storyboard_envelope = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard = VideoStoryboard.model_validate(storyboard_envelope["payload"])

    package_path = WORKFLOW_ROOT / storyboard.task_id / "audio-package-v001.json"
    package_envelope = json.loads(package_path.read_text(encoding="utf-8"))
    old_clips = package_envelope["payload"]["clips"]
    corrected: list[TtsGenerationResult] = []
    paths: list[Path] = []
    for old in old_clips:
        path = PROJECT_ROOT / old["file_path"]
        paths.append(path)
        duration = wav_duration(path.read_bytes())
        result = TtsGenerationResult.model_validate(
            {**old, "duration_seconds": round(duration, 3), "manifest_path": ""}
        )
        manifest = persist_version(result.scene_id, "tts-generation", result.model_dump())
        corrected.append(result.model_copy(update={"manifest_path": manifest}))

    combined_path = OUTPUT_ROOT / "narration-combined-v002.wav"
    total_duration = concatenate_wav(paths, combined_path)
    srt_path = write_actual_srt(
        storyboard,
        [result.duration_seconds for result in corrected],
    )
    package_manifest = persist_version(
        storyboard.task_id,
        "audio-package",
        {
            "model": corrected[0].model,
            "voice": corrected[0].voice,
            "clips": [result.model_dump() for result in corrected],
            "combined_file": str(combined_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "subtitle_file": str(srt_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "actual_duration_seconds": round(total_duration, 3),
            "metadata_repair": "duration_calculated_from_audio_bytes_not_streaming_header_placeholder",
            "additional_model_call": False,
            "human_science_review_required": True,
        },
    )
    print(
        json.dumps(
            {
                "clip_durations_seconds": [result.duration_seconds for result in corrected],
                "combined_duration_seconds": round(total_duration, 3),
                "combined_file": str(combined_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "package_manifest": package_manifest,
                "additional_model_call": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
