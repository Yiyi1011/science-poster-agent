from __future__ import annotations

import json
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = PROJECT_ROOT / "artifacts" / "video" / "solar-weather-v001"
POSTER_PATH = PROJECT_ROOT / "artifacts" / "solar-weather-poster-v2.png"
AUDIO_PATH = VIDEO_DIR / "narration-combined-v002.wav"
SRT_PATH = VIDEO_DIR / "subtitles-actual-v002.srt"
OUTPUT_PATH = VIDEO_DIR / "solar-weather-preview-v001.mp4"
COVER_PATH = VIDEO_DIR / "solar-weather-preview-cover-v001.png"
MANIFEST_PATH = VIDEO_DIR / "local-preview-manifest-v001.json"

WIDTH = 1280
HEIGHT = 720
FPS = 15


@dataclass(frozen=True)
class Subtitle:
    start: float
    end: float
    text: str


def parse_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, milliseconds = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def read_subtitles(path: Path) -> list[Subtitle]:
    blocks = re.split(r"\r?\n\r?\n", path.read_text(encoding="utf-8").strip())
    subtitles: list[Subtitle] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        start_text, end_text = lines[1].split(" --> ")
        subtitles.append(
            Subtitle(
                start=parse_timestamp(start_text),
                end=parse_timestamp(end_text),
                text="".join(lines[2:]),
            )
        )
    return subtitles


def actual_wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        frame_bytes = stream.getnchannels() * stream.getsampwidth()
        frame_rate = stream.getframerate()
        data_bytes = path.stat().st_size - 44
    return data_bytes / frame_bytes / frame_rate


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and draw.textbbox((0, 0), candidate, font=text_font)[2] > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def scene_for_time(seconds: float) -> tuple[int, str, int]:
    if seconds < 7.84:
        return 1, "三类信使，不同速度", 0
    if seconds < 22.80:
        return 2, "影响路径与成立条件", 520
    return 3, "机制、边界与风险降低", 925


def render_frame(
    poster: Image.Image,
    subtitles: list[Subtitle],
    seconds: float,
    duration: float,
) -> Image.Image:
    scene_number, scene_title, crop_y = scene_for_time(seconds)
    crop_y = min(crop_y, poster.height - 675)
    crop = poster.crop((0, crop_y, 1200, crop_y + 675))

    local_progress = (
        seconds / 7.84
        if scene_number == 1
        else (seconds - 7.84) / (22.80 - 7.84)
        if scene_number == 2
        else (seconds - 22.80) / max(duration - 22.80, 0.01)
    )
    zoom = 1.0 + 0.035 * max(0.0, min(local_progress, 1.0))
    resized = crop.resize((round(WIDTH * zoom), round(HEIGHT * zoom)), Image.Resampling.BICUBIC)
    x = max(0, (resized.width - WIDTH) // 2)
    y = max(0, round((resized.height - HEIGHT) * max(0.0, min(local_progress, 1.0))))
    frame = resized.crop((x, y, x + WIDTH, y + HEIGHT)).convert("RGB")

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((42, 34, 540, 94), radius=18, fill=(4, 22, 39, 215), outline=(84, 216, 232, 210), width=2)
    draw.text((62, 49), f"0{scene_number}  {scene_title}", font=font(25, bold=True), fill=(235, 248, 252, 255))

    active = next((item for item in subtitles if item.start <= seconds < item.end), None)
    if active:
        subtitle_font = font(28, bold=True)
        lines = wrap_text(draw, active.text, subtitle_font, WIDTH - 150)
        line_height = 43
        box_height = 44 + line_height * len(lines)
        top = HEIGHT - box_height - 26
        draw.rounded_rectangle((48, top, WIDTH - 48, HEIGHT - 26), radius=18, fill=(2, 15, 28, 225))
        for index, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=subtitle_font)
            text_width = bbox[2] - bbox[0]
            draw.text(((WIDTH - text_width) / 2, top + 20 + index * line_height), line, font=subtitle_font, fill=(255, 255, 255, 255))

    draw.rectangle((0, HEIGHT - 8, WIDTH, HEIGHT), fill=(17, 40, 58, 230))
    draw.rectangle((0, HEIGHT - 8, round(WIDTH * seconds / duration), HEIGHT), fill=(240, 80, 44, 255))
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def main() -> None:
    for path in (POSTER_PATH, AUDIO_PATH, SRT_PATH):
        if not path.exists():
            raise FileNotFoundError(path)
    poster = Image.open(POSTER_PATH).convert("RGB")
    subtitles = read_subtitles(SRT_PATH)
    duration = actual_wav_duration(AUDIO_PATH)
    total_frames = round(duration * FPS)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "pipe:0",
        "-i",
        str(AUDIO_PATH),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(OUTPUT_PATH),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    for frame_index in range(total_frames):
        seconds = frame_index / FPS
        frame = render_frame(poster, subtitles, seconds, duration)
        if frame_index == 0:
            frame.save(COVER_PATH)
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(stderr[-4000:])

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifact_kind": "local_preview_video",
        "cloud_model_calls": 0,
        "estimated_cloud_cost_cny": 0,
        "video": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "cover": str(COVER_PATH.relative_to(PROJECT_ROOT)),
        "poster_source": str(POSTER_PATH.relative_to(PROJECT_ROOT)),
        "audio_source": str(AUDIO_PATH.relative_to(PROJECT_ROOT)),
        "subtitle_source": str(SRT_PATH.relative_to(PROJECT_ROOT)),
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "frame_count": total_frames,
        "duration_seconds": round(duration, 3),
        "video_encoder": "libx264",
        "audio_encoder": "aac",
        "ffmpeg_provider": "imageio-ffmpeg 0.6.0",
        "subtitle_mode": "burned_in_from_reviewed_srt",
        "scene_boundaries_seconds": [0, 7.84, 22.80, round(duration, 3)],
        "human_review_required": True,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
