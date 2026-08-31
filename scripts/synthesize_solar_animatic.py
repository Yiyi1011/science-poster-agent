"""Versioned 7-scene Qwen narration. Dry-run by default; never retry uncertain charges.

The confirmed script stays unchanged. Every synthesis is checkpointed before the
request, so an interrupted run cannot silently submit a billable scene twice.
"""
from __future__ import annotations

import argparse
import asyncio
from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.models import VideoScene
from app.services.qwen_tts_client import QwenTtsClient
from app.services.usage_ledger import recorded_tts_cost

DIRECTORY = ROOT / "artifacts/video/solar-weather-v002-animation"
SOURCE = DIRECTORY / "storyboard-v003.json"
OUTPUT = DIRECTORY / "narration-v001"
RATE, FPS, SAMPLE_WIDTH = 24000, 24, 2
BATCH_CAP = 0.1


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, RATE)
        # Some stream WAVs use a placeholder frame count: measure decoded bytes.
        return audio.readframes(audio.getnframes())


async def main(execute: bool) -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    settings = Settings()
    settings.validate_for_tts()
    assert settings.qwen_tts_model == "qwen-audio-3.0-tts-flash", "Recheck model price before changing model."
    assert settings.qwen_tts_price_per_10k_chars == 1, "Recheck Beijing price."
    characters = sum(len(scene["narration_draft"].strip()) for scene in source["scenes"])
    estimate = round(characters / 10000, 6)
    assert estimate <= BATCH_CAP
    print(json.dumps({"dry_run": not execute, "scenes": len(source["scenes"]), "characters": characters,
                      "batch_estimate_cny": estimate, "batch_cap_cny": BATCH_CAP,
                      "tts_recorded_estimate_cny": recorded_tts_cost(), "credentials_present": bool(settings.dashscope_api_key)}), flush=True)
    if not execute:
        return
    assert recorded_tts_cost() + estimate <= settings.tts_budget_cny
    OUTPUT.mkdir(exist_ok=True)
    client = QwenTtsClient(settings)
    timeline, audio_parts = [], []
    total_frames = 0
    for scene in source["scenes"]:
        scene_id = scene["id"] + "-VOICE01"
        checkpoint = OUTPUT / f"{scene_id}.json"
        fingerprint = hashlib.sha256((scene["narration_draft"] + settings.qwen_tts_model + settings.qwen_tts_voice).encode()).hexdigest()
        if checkpoint.exists():
            record = json.loads(checkpoint.read_text(encoding="utf-8"))
            assert record["fingerprint"] == fingerprint, "Input changed: choose a new version."
            assert record["status"] == "completed", "Uncertain prior request: reconcile billing before any retry."
            result = record["result"]
            assert hashlib.sha256((ROOT / result["file_path"]).read_bytes()).hexdigest() == record["audio_sha256"]
        else:
            record = {"scene_id": scene_id, "fingerprint": fingerprint, "status": "pending",
                      "started_at": datetime.now(timezone.utc).isoformat(), "estimated_cost_cny": len(scene["narration_draft"].strip()) / 10000}
            save(checkpoint, record)
            try:
                result = (await client.generate(VideoScene(
                    scene_id=scene_id, duration_seconds=scene["duration_seconds"], heading=scene["title"],
                    source_claim_ids=scene["source_ids"], visual_prompt="Approved local Canvas cartoon; no image/video model request.",
                    narration=scene["narration_draft"], subtitle=" / ".join(scene["subtitle_cards"])), OUTPUT)).model_dump()
            except Exception as error:
                # Do not serialize exception text: it can contain signed URLs.
                record.update(status="failed_or_uncertain", error_type=type(error).__name__)
                save(checkpoint, record)
                print(json.dumps({"scene": scene_id, "status": "stopped", "error_type": type(error).__name__, "automatic_retry": False}), flush=True)
                raise SystemExit(1) from None
            record.update(status="completed", result=result,
                          audio_sha256=hashlib.sha256((ROOT / result["file_path"]).read_bytes()).hexdigest())
            save(checkpoint, record)
        pcm = read_pcm(ROOT / result["file_path"])
        samples = array("h", pcm)
        sample_count = len(samples)
        actual = sample_count / RATE
        # Natural voice drives the cut; reserve >=2.5s per short summary card.
        # Original silent version remains untouched; never speed up the speech.
        frames = max(math.ceil(len(scene["subtitle_cards"]) * 2.5 * FPS), math.ceil((actual + 0.8) * FPS))
        leading_samples = int(0.15 * RATE)
        trailing_samples = frames * (RATE // FPS) - sample_count - leading_samples
        assert trailing_samples >= 0
        audio_parts.append(b"\0\0" * leading_samples + pcm + b"\0\0" * trailing_samples)
        timeline.append({**scene, "start_seconds": total_frames / FPS, "duration_seconds": frames / FPS,
                         "original_duration_seconds": scene["duration_seconds"], "frames": frames,
                         "narration_start_seconds": total_frames / FPS + 0.15, "narration_duration_seconds": actual,
                         "narration_end_seconds": total_frames / FPS + 0.15 + actual,
                         "tts": result, "peak_amplitude": max(abs(s) for s in samples) / 32768,
                         "rms_amplitude": math.sqrt(sum(s*s for s in samples) / sample_count) / 32768,
                         "clipped_sample_fraction": sum(abs(s) >= 32767 for s in samples) / sample_count})
        total_frames += frames
        print(json.dumps({"scene": scene_id, "audio_seconds": round(actual, 3), "scene_seconds": frames / FPS, "status": "saved"}), flush=True)
    destination = OUTPUT / "narration-timeline-v001.wav"
    with wave.open(str(destination), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(SAMPLE_WIDTH)
        audio.setframerate(RATE)
        audio.writeframes(b"".join(audio_parts))
    save(OUTPUT / "timeline-v001.json", {
        "version": 1, "status": "synthesized_awaiting_listening_review", "fps": FPS,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "duration_seconds": total_frames / FPS, "frames": total_frames, "characters": characters,
        "model": settings.qwen_tts_model, "voice": settings.qwen_tts_voice,
        "estimated_cost_cny": estimate, "actual_paid_cny": None,
        "audio_path": destination.relative_to(ROOT).as_posix(),
        "audio_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "scene_silence_policy": "150ms lead; >=650ms tail; >=2.5s per summary card; no voice speedup",
        "scenes": timeline,
    })
    print(json.dumps({"status": "completed", "duration_seconds": total_frames / FPS, "estimated_cost_cny": estimate}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Make at most seven billable calls; resume completed checkpoints only.")
    asyncio.run(main(parser.parse_args().execute))
