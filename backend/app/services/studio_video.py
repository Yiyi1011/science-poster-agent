"""Local illustrated-video compositor. All words are supplied by the reviewed script.

Images are scaled inside the frame (not cropped, preserving provider watermarks).
Subtitle timing is weighted within each actual voice clip, not forced alignment.
"""
import math
import os
from pathlib import Path
import subprocess
import wave

from PIL import Image, ImageDraw, ImageFont, ImageOps
import imageio_ffmpeg

W, H, FPS = 1280, 720, 12


def find_font():
    candidates = [os.getenv("SCIVIS_FONT_PATH", ""), "C:/Windows/Fonts/msyh.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("Chinese font missing; configure SCIVIS_FONT_PATH")


def wrap_pixels(value, font, width):
    result, line = [], ""
    for char in value:
        if line and font.getlength(line + char) > width:
            result.append(line)
            line = ""
        line += char
    return result + [line] if line else result


def write_text(draw, text, xy, font, width, fill):
    x, y = xy
    line_height = font.size + 12
    for line in wrap_pixels(text, font, width):
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def srt_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def wav_pcm_duration(path):
    """Use bytes actually present; some Qwen WAV downloads advertise an oversized data chunk."""
    with wave.open(str(path), "rb") as audio:
        frame_bytes = audio.readframes(audio.getnframes())
        bytes_per_frame = audio.getnchannels() * audio.getsampwidth()
        return len(frame_bytes) / bytes_per_frame / audio.getframerate()


def combine_audio(paths, target, pad_to_total=0):
    signature, chunks, durations = None, [], []
    for path in paths:
        with wave.open(str(path), "rb") as audio:
            current = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype())
            if signature and signature != current:
                raise ValueError("Incompatible voice clips")
            signature = current
            chunks.append(audio.readframes(audio.getnframes()))
            durations.append(len(chunks[-1]) / (current[0] * current[1] * current[2]))
    if not signature:
        raise ValueError("No voice clips")
    with wave.open(str(target), "wb") as output:
        output.setnchannels(signature[0]); output.setsampwidth(signature[1]); output.setframerate(signature[2])
        padding = max(0.7, min(3.5, (pad_to_total-sum(durations))/len(durations))) if pad_to_total else 0
        silence = b"\0" * (round(padding / 2 * signature[2]) * signature[0] * signature[1])
        for chunk in chunks:
            output.writeframes(silence + chunk + silence)
    if pad_to_total:
        actual_padding = len(silence) * 2 / (signature[0] * signature[1] * signature[2])
        durations = [duration + actual_padding for duration in durations]
    return durations


def illustrated_poster(draft, image, target, font_path):
    fonts = {n: ImageFont.truetype(font_path, n) for n in (22, 28, 34, 52)}
    # Generous canvas first, then crop unused blank bottom only (never the illustration).
    canvas = Image.new("RGB", (1080, 3200), "#08252f")
    draw = ImageDraw.Draw(canvas)
    y = write_text(draw, draft.title, (64, 60), fonts[52], 952, "#ffffff") + 24
    y = write_text(draw, draft.takeaway, (64, y), fonts[28], 952, "#ffda83") + 30
    hero = ImageOps.contain(image, (952, 560))
    canvas.paste(hero, ((1080 - hero.width) // 2, y))
    y += hero.height + 24
    y = write_text(draw, "AI概念插画 · 不是实物照片或测量数据", (64, y), fonts[22], 952, "#75d9c4") + 32
    if draft.public_poster:
        for card in [draft.public_poster.example, *draft.public_poster.cards, draft.public_poster.caution]:
            y = write_text(draw, card.heading, (64, y), fonts[34], 952, "#ffda83") + 10
            y = write_text(draw, card.body, (64, y), fonts[28], 952, "#ffffff") + 26
    y = write_text(draw, "AI生成预览 · 待科学与视觉终审；来源与修改记录见项目证据页。", (64, y), fonts[22], 952, "#75d9c4")
    if y + 50 > canvas.height:
        raise ValueError("Poster text overflow")
    canvas.crop((0, 0, 1080, y + 50)).save(target)


def compose(draft, image_paths, audio_paths, folder, cartoon_plans=None):
    if len(image_paths) != len(draft.scenes) or len(audio_paths) != len(draft.scenes):
        raise ValueError("Every scene requires an approved illustration and voice")
    font_path = find_font()
    title_font, subtitle_font, small_font = [ImageFont.truetype(font_path, n) for n in (36, 32, 20)]
    images = [Image.open(p).convert("RGB") for p in image_paths]
    voice_durations=[wav_pcm_duration(path) for path in audio_paths]
    durations = combine_audio(audio_paths, folder / "combined.wav", 68 if cartoon_plans else 0)
    fps = 20 if cartoon_plans else FPS
    end_times, cursor, captions, subtitles = [], 0.0, [], []
    for scene, duration, voice_duration in zip(draft.scenes, durations, voice_durations, strict=True):
        pieces = [scene.narration[i:i + 22] for i in range(0, len(scene.narration), 22)]
        t = cursor + (duration - voice_duration) / 2
        for piece in pieces:
            end = t + voice_duration * len(piece) / len(scene.narration)
            captions.append((t, end, piece))
            subtitles.append(f"{len(captions)}\n{srt_time(t)} --> {srt_time(end)}\n{piece}\n")
            t = end
        cursor += duration
        end_times.append(cursor)
    previous_end = 0.0
    for start, end, _ in captions:
        if start < previous_end - 1e-6 or start < 0 or end <= start or end > cursor + 1e-6:
            raise ValueError("Subtitle timeline is outside the actual video duration")
        previous_end = end
    (folder / "subtitles.srt").write_text("\n".join(subtitles), encoding="utf-8")
    if not cartoon_plans:
        illustrated_poster(draft, images[0], folder / "poster.png", font_path)
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0", "-i", str(folder / "combined.wav"),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", "-movflags", "+faststart", str(folder / "preview.mp4")]
    with (folder / "compose.log").open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            scene_index, caption_index = 0, 0
            for frame in range(math.ceil(cursor * fps)):
                seconds = frame / fps
                while scene_index < len(end_times) - 1 and seconds >= end_times[scene_index]:
                    scene_index += 1
                while caption_index < len(captions) - 1 and seconds >= captions[caption_index][1]:
                    caption_index += 1
                start = end_times[scene_index - 1] if scene_index else 0
                phase = min(1.0, (seconds - start) / durations[scene_index])
                if cartoon_plans:
                    from app.services.studio_cartoon import frame as cartoon_frame
                    canvas = cartoon_frame(cartoon_plans[scene_index], phase, draft.scenes[scene_index].heading)
                else:
                    scale = 0.94 + 0.06 * phase
                    art = ImageOps.contain(images[scene_index], (int(1140 * scale), int(490 * scale)))
                    canvas = Image.new("RGB", (W, H), "#08252f")
                    canvas.paste(art, ((W - art.width) // 2, 92 + (490 - art.height) // 2))
                draw = ImageDraw.Draw(canvas)
                if not cartoon_plans:
                    draw.text((44, 18), f"{scene_index + 1:02}  {draft.scenes[scene_index].heading}", font=title_font, fill="#ffda83")
                    draw.text((44, 64), "AI插画有声预览 · 概念类比 · 待终审", font=small_font, fill="#75d9c4")
                draw.rounded_rectangle((42, 598, W - 42, 685), radius=16, fill="#174550")
                cap_start, cap_end, cap_text = captions[caption_index]
                caption = cap_text if cap_start <= seconds < cap_end else ""
                draw.text(((W - subtitle_font.getlength(caption)) / 2, 620), caption, font=subtitle_font, fill="white")
                draw.rectangle((0, H - 6, W * seconds / cursor, H), fill="#ffda83")
                if cartoon_plans:
                    draw.text((44, 689), "千问规划 · 程序卡通动画 · AI旁白 · 待人工终审",font=small_font,fill="#75d9c4")
                process.stdin.write(canvas.tobytes())
            process.stdin.close()
            if process.wait(timeout=60) != 0:
                raise RuntimeError("Video encoding failed")
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
    return {"duration_seconds": round(cursor, 3), "resolution": [W, H], "fps": fps,
            "video": "preview.mp4", **({"poster": "poster.png"} if not cartoon_plans else {}), "subtitles": "subtitles.srt",
            "timing_note": "逐镜采用真实配音时长；镜内字幕按字数分配，非逐字强制对齐"}
