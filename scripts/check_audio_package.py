from __future__ import annotations

import json
import math
import re
import sys
import wave
from array import array
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "video" / "solar-weather-v001"

sys.path.insert(0, str(BACKEND_ROOT))

from app.services.visual_workflow import persist_version  # noqa: E402


TASK_ID = "e227ed71-e128-4ae7-9da4-a0db070e56b3"


def inspect_wav(path: Path) -> dict:
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        rate = audio.getframerate()
        raw = audio.readframes(audio.getnframes())
    if width != 2:
        raise RuntimeError(f"Unsupported sample width: {width}")
    samples = array("h")
    samples.frombytes(raw)
    peak = max((abs(value) for value in samples), default=0)
    rms = math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
    clipping_ratio = sum(abs(value) >= 32760 for value in samples) / max(1, len(samples))
    near_silence_ratio = sum(abs(value) < 64 for value in samples) / max(1, len(samples))
    duration = len(raw) / (channels * width * rate)
    return {
        "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "channels": channels,
        "sample_width_bytes": width,
        "sample_rate_hz": rate,
        "duration_seconds": round(duration, 3),
        "peak_normalized": round(peak / 32768, 4),
        "rms_normalized": round(rms / 32768, 4),
        "clipping_ratio": round(clipping_ratio, 6),
        "near_silence_ratio": round(near_silence_ratio, 4),
        "technical_pass": (
            channels == 1
            and width == 2
            and rate == 24000
            and duration > 1
            and rms > 100
            and clipping_ratio < 0.001
        ),
    }


def srt_end_seconds(path: Path) -> float:
    text = path.read_text(encoding="utf-8-sig")
    matches = re.findall(r"-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})", text)
    hours, minutes, seconds, millis = map(int, matches[-1])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def main() -> None:
    clips = sorted((OUTPUT_ROOT / "audio-clips").glob("*.wav"))
    combined = OUTPUT_ROOT / "narration-combined-v002.wav"
    subtitle = OUTPUT_ROOT / "subtitles-actual-v002.srt"
    reports = [inspect_wav(path) for path in clips]
    combined_report = inspect_wav(combined)
    subtitle_end = srt_end_seconds(subtitle)
    duration_match = abs(subtitle_end - combined_report["duration_seconds"]) <= 0.02
    technical_pass = all(item["technical_pass"] for item in reports + [combined_report]) and duration_match
    payload = {
        "status": "technical_pass_needs_human_listening_review" if technical_pass else "technical_fail",
        "clips": reports,
        "combined": combined_report,
        "subtitle_end_seconds": subtitle_end,
        "subtitle_duration_match": duration_match,
        "checks": {
            "container": "RIFF/WAVE readable",
            "target_format": "mono PCM16 24kHz",
            "non_silent": True,
            "clipping_threshold": 0.001,
        },
        "human_review_remaining": [
            "中文发音与缩写读法",
            "科普语气是否自然",
            "字幕断句与画面节奏",
            "事实表述与最终画面一致性",
        ],
        "additional_model_call": False,
    }
    manifest = persist_version(TASK_ID, "audio-review", payload)
    print(json.dumps({**payload, "manifest_path": manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
