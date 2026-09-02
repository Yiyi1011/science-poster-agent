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
                  "/System/Library/Fonts/PingFang.ttc",
                  "/System/Library/Fonts/STHeiti Medium.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("Chinese font missing; configure SCIVIS_FONT_PATH")


def wrap_pixels(value, font, width):
    result, line = [], ""
    # Chinese punctuation belongs to the preceding phrase.  Keeping it there may
    # exceed the target width by one glyph, but avoids a lone full stop/comma on
    # the next subtitle line (which reads like a broken sentence to viewers).
    trailing_punctuation = set("，。！？；：、）》」』】”’…—,.;:!?)]}")
    for char in value:
        if line and font.getlength(line + char) > width:
            if char in trailing_punctuation:
                line += char
                continue
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


def complete_sentence_captions(value):
    """Keep complete sentences in one timed cue; visual wrapping is handled separately."""
    text = value.strip()
    if not text:
        return []
    endings = set("。！？!?．.")
    closers = set("”’\"'」』）)]")
    pieces, current, ended = [], "", False
    for char in text:
        if ended and char not in closers:
            pieces.append(current.strip())
            current, ended = char, char in endings
        else:
            current += char
            if char in endings:
                ended = True
    if current.strip():
        tail = current.strip()
        # A short unpunctuated tail is usually a fragment of the preceding sentence.
        if pieces and not any(tail.endswith(mark) for mark in endings) and len(tail) <= 12:
            pieces[-1] += tail
        else:
            pieces.append(tail)
    return pieces


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


def _captioned_slide(source_path, target, caption, seconds, total, subtitle_font, small_font):
    """Render one still per subtitle interval instead of hundreds of Python frames."""
    with Image.open(source_path) as source:
        source = source.convert("RGB")
        if source.size == (W, H):
            canvas = source.copy()
        else:
            art = ImageOps.contain(source, (W, H))
            canvas = Image.new("RGB", (W, H), "#08252f")
            canvas.paste(art, ((W - art.width) // 2, (H - art.height) // 2))
    try:
        draw = ImageDraw.Draw(canvas)
        caption_lines = wrap_pixels(caption, subtitle_font, W - 140)
        line_height = subtitle_font.size + 9
        box_height = max(87, len(caption_lines) * line_height + 28)
        box_top, box_bottom = 685 - box_height, 685
        draw.rounded_rectangle((42, box_top, W - 42, box_bottom), radius=16, fill="#174550")
        text_y = box_top + (box_height - len(caption_lines) * line_height) / 2
        for line in caption_lines:
            draw.text(((W - subtitle_font.getlength(line)) / 2, text_y), line,
                      font=subtitle_font, fill="white")
            text_y += line_height
        draw.rectangle((0, H - 6, W * seconds / total, H), fill="#ffda83")
        draw.text((44, 689), "SCIVIS · 科普视频", font=small_font, fill="#75d9c4")
        canvas.save(target)
    finally:
        canvas.close()


def _encode_cartoon_slides(image_paths, captions, end_times, total, folder, subtitle_font, small_font):
    intervals = []
    scene_start = 0.0
    for scene_index, scene_end in enumerate(end_times):
        position = scene_start
        scene_captions = [(start, end, text) for start, end, text in captions
                          if start >= scene_start - 1e-6 and end <= scene_end + 1e-6]
        for start, end, text in scene_captions:
            if start > position + 0.001:
                intervals.append((scene_index, position, start, ""))
            intervals.append((scene_index, start, end, text))
            position = end
        if scene_end > position + 0.001:
            intervals.append((scene_index, position, scene_end, ""))
        scene_start = scene_end
    if not intervals:
        raise ValueError("No video intervals")
    slides = []
    for index, (scene_index, start, end, caption) in enumerate(intervals, 1):
        path = folder / f"compose-slide-{index:03}.png"
        _captioned_slide(image_paths[scene_index], path, caption, (start + end) / 2,
                         total, subtitle_font, small_font)
        slides.append((path, end - start))
    concat = folder / "compose-slides.ffconcat"
    lines = ["ffconcat version 1.0"]
    for path, duration in slides:
        lines.extend((f"file '{path.name}'", f"duration {duration:.6f}"))
    lines.append(f"file '{slides[-1][0].name}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(folder / "combined.wav"),
        "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
        "-tune", "stillimage", "-threads", "1", "-crf", "23", "-c:a", "aac",
        "-shortest", "-movflags", "+faststart", str(folder / "preview.mp4")]
    with (folder / "compose.log").open("wb") as log:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0:
        raise RuntimeError("Video encoding failed")


def compose(draft, image_paths, audio_paths, folder, cartoon_plans=None, planning_label="千问规划"):
    if len(image_paths) != len(draft.scenes) or len(audio_paths) != len(draft.scenes):
        raise ValueError("Every scene requires an approved illustration and voice")
    font_path = find_font()
    title_font, subtitle_font, small_font = [ImageFont.truetype(font_path, n) for n in (36, 32, 20)]
    # Cartoon frames are drawn from plans and never use the accepted preview
    # PNGs.  Avoid decoding all of them in FC before starting FFmpeg.
    images = [] if cartoon_plans else [Image.open(p).convert("RGB") for p in image_paths]
    voice_durations=[wav_pcm_duration(path) for path in audio_paths]
    durations = combine_audio(audio_paths, folder / "combined.wav", 68 if cartoon_plans else 0)
    fps = FPS
    end_times, cursor, captions, subtitles = [], 0.0, [], []
    for scene, duration, voice_duration in zip(draft.scenes, durations, voice_durations, strict=True):
        pieces = complete_sentence_captions(scene.narration)
        t = cursor + (duration - voice_duration) / 2
        for piece in pieces:
            end = t + voice_duration * len(piece) / len(scene.narration)
            captions.append((t, end, piece))
            screen_lines = "\n".join(wrap_pixels(piece, subtitle_font, W - 140))
            subtitles.append(f"{len(captions)}\n{srt_time(t)} --> {srt_time(end)}\n{screen_lines}\n")
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
    else:
        _encode_cartoon_slides(image_paths, captions, end_times, cursor, folder,
                               subtitle_font, small_font)
        return {"duration_seconds": round(cursor, 3), "resolution": [W, H], "fps": fps,
                "video": "preview.mp4", "subtitles": "subtitles.srt",
                "timing_note": "逐镜采用真实配音时长；现有分镜按完整句字幕生成低内存关键帧并合成为视频"}
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0", "-i", str(folder / "combined.wav"),
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-threads", "1",
        "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", "-movflags", "+faststart", str(folder / "preview.mp4")]
    with (folder / "compose.log").open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
            bufsize=0, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
                try:
                    draw = ImageDraw.Draw(canvas)
                    if not cartoon_plans:
                        draw.text((44, 18), f"{scene_index + 1:02}  {draft.scenes[scene_index].heading}", font=title_font, fill="#ffda83")
                        draw.text((44, 64), "SCIVIS · 科普视频", font=small_font, fill="#75d9c4")
                    cap_start, cap_end, cap_text = captions[caption_index]
                    caption = cap_text if cap_start <= seconds < cap_end else ""
                    caption_lines = wrap_pixels(caption, subtitle_font, W - 140)
                    line_height = subtitle_font.size + 9
                    box_height = max(87, len(caption_lines) * line_height + 28)
                    box_top, box_bottom = 685 - box_height, 685
                    draw.rounded_rectangle((42, box_top, W - 42, box_bottom), radius=16, fill="#174550")
                    text_y = box_top + (box_height - len(caption_lines) * line_height) / 2
                    for line in caption_lines:
                        draw.text(((W - subtitle_font.getlength(line)) / 2, text_y), line, font=subtitle_font, fill="white")
                        text_y += line_height
                    draw.rectangle((0, H - 6, W * seconds / cursor, H), fill="#ffda83")
                    if cartoon_plans:
                        draw.text((44, 689), "SCIVIS · 科普视频", font=small_font, fill="#75d9c4")
                    process.stdin.write(canvas.tobytes())
                finally:
                    canvas.close()
            process.stdin.close()
            if process.wait(timeout=60) != 0:
                raise RuntimeError("Video encoding failed")
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
    return {"duration_seconds": round(cursor, 3), "resolution": [W, H], "fps": fps,
            "video": "preview.mp4", **({"poster": "poster.png"} if not cartoon_plans else {}), "subtitles": "subtitles.srt",
            "timing_note": "逐镜采用真实配音时长；完整句子保持在同一字幕块并在画面内换行，非逐字强制对齐"}


def verify_media_output(folder, video_name="preview.mp4", subtitle_name="subtitles.srt"):
    """Post-compose integrity (brief 6.1.10): decode the final MP4, read duration, audio
    track and three sample frames. Evidence lands in the job manifest, never a fake pass."""
    import re
    path = folder / video_name
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    info = probe.stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info)
    duration = None
    if match:
        hours, minutes, seconds = (int(match.group(1)), int(match.group(2)), float(match.group(3)))
        duration = round(hours * 3600 + minutes * 60 + seconds, 3)
    has_audio = "Audio:" in info
    frames = []
    try:
        if duration is None or duration <= 0:
            raise ValueError("视频没有可读取的时长")
        # Inspect the whole programme, not three nearly identical frames from its first second.
        for index, fraction in enumerate((0.25, 0.5, 0.75), 1):
            frame_path = folder / f"integrity-frame-{index}.png"
            position = f"{duration * fraction:.3f}"
            subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", position,
                            "-i", str(path), "-frames:v", "1", str(frame_path)], check=True,
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            frames.append(frame_path.name)
    except (subprocess.CalledProcessError, ValueError) as exc:
        return {"status": "failed", "error": "视频解码失败", "detail": type(exc).__name__,
                "duration_seconds": duration, "has_audio": has_audio}
    subtitle_path = folder / subtitle_name
    subtitle_check = verify_subtitles(subtitle_path, duration) if subtitle_path.is_file() else {
        "status": "failed", "error": "缺少字幕文件", "cue_count": 0}
    if duration is None or not has_audio or len(frames) != 3 or subtitle_check["status"] != "ok":
        return {"status": "failed", "error": "时长或音轨未通过", "duration_seconds": duration,
                "has_audio": has_audio, "sample_frames": frames, "subtitles": subtitle_check}
    return {"status": "ok", "duration_seconds": duration, "has_audio": has_audio,
            "sample_frames": frames, "sample_positions_seconds": [round(duration * f, 3) for f in (0.25, 0.5, 0.75)],
            "subtitles": subtitle_check}


def verify_subtitles(path, video_duration):
    """Check an exported SRT independently from the in-memory compose timeline."""
    import re
    content = path.read_text(encoding="utf-8").strip()
    blocks = [block for block in re.split(r"\r?\n\r?\n", content) if block.strip()]
    previous_end, incomplete = 0.0, []

    def seconds(value):
        match = re.fullmatch(r"(\d+):(\d+):(\d+),(\d{3})", value.strip())
        if not match:
            raise ValueError("invalid timestamp")
        hours, minutes, secs, millis = map(int, match.groups())
        return hours * 3600 + minutes * 60 + secs + millis / 1000

    try:
        for index, block in enumerate(blocks, 1):
            lines = block.splitlines()
            if len(lines) < 3 or " --> " not in lines[1]:
                raise ValueError("invalid cue")
            start_text, end_text = lines[1].split(" --> ", 1)
            start, end = seconds(start_text), seconds(end_text)
            text = "".join(lines[2:]).strip()
            if not text or start < previous_end - 0.002 or end <= start or end > video_duration + 0.1:
                raise ValueError("cue outside timeline")
            if text[-1] not in "。！？!?．.…”’\"'」』）)]":
                incomplete.append(index)
            previous_end = end
    except ValueError as exc:
        return {"status": "failed", "error": str(exc), "cue_count": len(blocks)}
    if not blocks or incomplete:
        return {"status": "failed", "error": "字幕存在不完整句子", "cue_count": len(blocks),
                "incomplete_cues": incomplete}
    return {"status": "ok", "cue_count": len(blocks), "last_end_seconds": round(previous_end, 3)}
