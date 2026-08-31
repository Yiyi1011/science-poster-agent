"""Validate the exported silent animatic, not just its browser source."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'artifacts/video/solar-weather-v002-animation'
VIDEO = DIRECTORY / 'solar-messengers-silent-v001.mp4'
MANIFEST = DIRECTORY / 'mp4-export-manifest-v001.json'

def seconds(value: str) -> float:
    h, m, rest = value.split(':')
    s, ms = rest.split(',')
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    reader = imageio_ffmpeg.read_frames(str(VIDEO))
    metadata = next(reader)
    reader.close()
    frame_count, duration = imageio_ffmpeg.count_frames_and_secs(str(VIDEO))
    blocks = re.split(r'\r?\n\r?\n', (DIRECTORY / 'subtitles-summary-timed-v001.srt').read_text(encoding='utf-8').strip())
    cues = []
    for block in blocks:
        lines = block.splitlines()
        start, end = lines[1].split(' --> ')
        cues.append((seconds(start), seconds(end), ''.join(lines[2:])))
    checks = {
        'video_sha_matches': hashlib.sha256(VIDEO.read_bytes()).hexdigest() == manifest['video_sha256'],
        'codec_h264': metadata['codec'] == 'h264',
        'size_1280_720': tuple(metadata['size']) == (1280, 720),
        'fps_24': metadata['fps'] == 24,
        'all_2016_frames_decoded': frame_count == 2016,
        'duration_84_seconds': abs(duration - 84) < 0.02,
        'nineteen_subtitle_cards': len(cues) == 19,
        'subtitle_characters_at_most_18': all(len(text) <= 18 for _, _, text in cues),
        'positive_cue_duration': all(end > start for start, end, _ in cues),
        'continuous_subtitles': all(abs(cues[i][1]-cues[i+1][0]) < 0.002 for i in range(len(cues)-1)),
        'subtitle_end_matches_video': abs(cues[-1][1] - duration) < 0.02,
    }
    assert all(checks.values()), checks
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    for moment in [29, 57, 80]:
        target = DIRECTORY / f'decoded-frame-{moment}s-v001.png'
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(moment), '-i', str(VIDEO), '-frames:v', '1', str(target)], check=True, capture_output=True)
    report = {'status': 'passed', 'checks': checks, 'metadata': metadata, 'decoded_frames': frame_count,
              'subtitle_kind': 'summary_cards_not_verbatim_transcription', 'audio_status': 'not_generated',
              'awaiting': ['AI narration after billing confirmation', 'visual/audio synchronization review', 'formal audience and science review']}
    (DIRECTORY / 'mp4-technical-review-v001.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
