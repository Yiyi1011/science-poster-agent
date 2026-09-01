from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models import TtsGenerationResult, VideoScene
from app.services.bailian_app_client import workspace_origin
from app.services.qwen_image_client import secure_aliyun_result_url
from app.services.usage_ledger import record_tts_usage, recorded_tts_cost
from app.services.visual_workflow import persist_version


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def parse_tts_response(body: dict[str, Any]) -> tuple[str, str]:
    output = body.get("output") or {}
    audio = output.get("audio") or {}
    url = str(audio.get("url") or output.get("url") or "")
    if not url:
        raise RuntimeError("TTS response contains no audio URL.")
    return url, str(body.get("request_id") or body.get("requestId") or "")


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as audio:
        frame_bytes = audio.readframes(audio.getnframes())
        bytes_per_frame = audio.getnchannels() * audio.getsampwidth()
        return len(frame_bytes) / bytes_per_frame / audio.getframerate()


class QwenTtsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, scene: VideoScene, output_dir: Path) -> TtsGenerationResult:
        self.settings.validate_for_tts()
        character_count = len(scene.narration.strip())
        estimated = character_count / 10_000 * self.settings.qwen_tts_price_per_10k_chars
        if recorded_tts_cost() + estimated > self.settings.tts_budget_cny:
            raise RuntimeError("TTS sub-budget would be exceeded.")

        url = f"{workspace_origin(self.settings)}/api/v1/services/audio/tts/SpeechSynthesizer"
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.qwen_tts_model,
            "input": {
                "text": scene.narration,
                "voice": self.settings.qwen_tts_voice,
                "format": "wav",
                "sample_rate": 24000,
            },
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            audio_url, request_id = parse_tts_response(response.json())
            try:
                audio_url = secure_aliyun_result_url(audio_url)
                audio_response = await client.get(audio_url)
                audio_response.raise_for_status()
            except Exception:
                # The synthesis may already be billable even when local URL validation/download fails.
                record_tts_usage(
                    self.settings,
                    request_id=request_id,
                    character_count=character_count,
                    duration_seconds=0,
                )
                raise
        duration = wav_duration(audio_response.content)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{scene.scene_id}.wav"
        path.write_bytes(audio_response.content)
        cost = record_tts_usage(
            self.settings,
            request_id=request_id,
            character_count=character_count,
            duration_seconds=duration,
        )
        try:
            stored_path = path.relative_to(PROJECT_ROOT)
        except ValueError:
            stored_path = path
        result = TtsGenerationResult(
            scene_id=scene.scene_id,
            model=self.settings.qwen_tts_model,
            voice=self.settings.qwen_tts_voice,
            file_path=str(stored_path).replace("\\", "/"),
            character_count=character_count,
            duration_seconds=round(duration, 3),
            estimated_cost_cny=cost,
            request_id=request_id,
        )
        manifest = persist_version(scene.scene_id, "tts-generation", result.model_dump())
        return result.model_copy(update={"manifest_path": manifest})
