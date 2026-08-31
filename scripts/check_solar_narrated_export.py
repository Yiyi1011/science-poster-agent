"""Offline QA of the actual muxed movie, including decoded narration alignment."""
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "artifacts/video/solar-weather-v002-animation"


def seconds(value: str) -> float:
    h, m, s = value.replace(",", ".").split(":")
    return int(h)*3600 + int(m)*60 + float(s)


def main() -> None:
    manifest = json.loads((DIRECTORY / "mp4-narrated-manifest-v001.json").read_text(encoding="utf-8"))
    timeline = json.loads((DIRECTORY / "narration-v001/timeline-v001.json").read_text(encoding="utf-8"))
    video = ROOT / manifest["video"]
    reader = imageio_ffmpeg.read_frames(str(video))
    metadata = next(reader)
    reader.close()
    frames, duration = imageio_ffmpeg.count_frames_and_secs(str(video))
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Decode every video/audio packet; don't confuse a valid header with a valid movie.
    subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True, capture_output=True)
    result = subprocess.run([ffmpeg, "-v", "error", "-i", str(video), "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", "24000", "pipe:1"], check=True, capture_output=True)
    decoded = array("h", result.stdout)
    with wave.open(str(ROOT / timeline["audio_path"]), "rb") as audio:
        source = array("h", audio.readframes(audio.getnframes()))
    checks = {
        "video_sha_matches": hashlib.sha256(video.read_bytes()).hexdigest() == manifest["video_sha256"],
        "audio_source_sha_matches": hashlib.sha256((ROOT / timeline["audio_path"]).read_bytes()).hexdigest() == timeline["audio_sha256"],
        "h264_1280x720_24fps": metadata["codec"] == "h264" and tuple(metadata["size"]) == (1280, 720) and metadata["fps"] == 24,
        "all_expected_frames_decoded": frames == timeline["frames"],
        "video_duration_matches_timeline": abs(duration - timeline["duration_seconds"]) < 1/24,
        "audio_duration_within_aac_padding": abs(len(decoded) - len(source)) < 2048,
        "seven_recorded_tts_requests": len(timeline["scenes"]) == 7 and all(s["tts"]["request_id"] for s in timeline["scenes"]),
        "source_voice_not_clipped": all(s["clipped_sample_fraction"] < 0.001 for s in timeline["scenes"]),
        "source_voice_non_silent": all(s["rms_amplitude"] > 0.003 for s in timeline["scenes"]),
        "no_voice_overlaps_scene_cuts": all(s["narration_end_seconds"] <= s["start_seconds"]+s["duration_seconds"] for s in timeline["scenes"]),
    }
    alignment = []
    for scene in timeline["scenes"]:
        start = round(scene["narration_start_seconds"] * 24000)
        end = round(scene["narration_end_seconds"] * 24000)
        a, b = source[start:end], decoded[start:end]
        norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
        cosine = sum(x*y for x, y in zip(a, b)) / norm if norm else 0
        alignment.append({"scene": scene["id"], "decoded_audio_cosine_at_expected_offset": round(cosine, 6)})
        checks[f"{scene['id']}_narration_in_expected_scene"] = cosine > 0.9
    cues = []
    blocks = re.split(r"\r?\n\r?\n", (DIRECTORY / "subtitles-summary-narrated-v001.srt").read_text(encoding="utf-8").strip())
    for block in blocks:
        lines = block.splitlines()
        start, end = lines[1].split(" --> ")
        cues.append((seconds(start), seconds(end), "".join(lines[2:])))
    checks.update({
        "nineteen_summary_subtitles": len(cues) == 19,
        "short_subtitles": all(len(text) <= 18 for _, _, text in cues),
        "subtitles_readable_time": all(end-start >= 2.49 for start, end, _ in cues),
        "continuous_subtitles": all(abs(cues[i][1]-cues[i+1][0]) < 0.002 for i in range(len(cues)-1)),
        "last_subtitle_matches_movie_end": abs(cues[-1][1]-timeline["duration_seconds"]) < 0.002,
    })
    qa = DIRECTORY / "qa-narrated-v001"
    qa.mkdir(exist_ok=True)
    for i, scene in enumerate(timeline["scenes"], 1):
        moment = scene["start_seconds"] + scene["duration_seconds"] * 0.65
        subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", str(moment), "-i", str(video), "-frames:v", "1", str(qa / f"scene-{i}.png")], check=True, capture_output=True)
    report = {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "metadata": metadata,
              "frames": frames, "duration_seconds": duration, "decoded_audio_seconds": len(decoded)/24000,
              "audio_alignment": alignment, "subtitle_kind": "summary_cards_not_verbatim_or_word_aligned",
              "pronunciation_listening_review": "awaiting_user", "final_submission_ready": False}
    (DIRECTORY / "mp4-narrated-technical-review-v001.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(checks.values()), checks


if __name__ == "__main__":
    main()
