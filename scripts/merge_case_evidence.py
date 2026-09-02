"""Consolidate the multi-case evidence directory into one summary.json.

Each successful run of scripts/test_multi_cases.py overwrites
evidence/multi-case-20260902/summary.json with only its own cases, while the
per-case artifact directories (preview.mp4 + frames) persist. This script
re-probes every persisted artifact and merges them with the authoritative
run/media outcomes recorded per case in the run logs, producing the final
consolidated acceptance record for the 2026-09-02 multi-case test.

Usage:
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe scripts/merge_case_evidence.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "multi-case-20260902"

# dir-prefix -> (topic, full project id, run outcome, media outcome, note)
# Outcomes come from the verified run logs (2026-09-02):
#   b3tj3pz8c 3-case batch, beevdfyrl 5-case batch, bnkrq5u0v final EXE run.
CASES = {
    "eccee23b": ("为什么蜜蜂飞的时候会发出嗡嗡声？", "eccee23b-9e04-4223-8a87-8897e06b095b",
                 "succeeded", "succeeded", "直通完成（run 审核两轮通过）"),
    "7cd54bc0": ("为什么铁会生锈？", "7cd54bc0-5b53-42a1-baa2-6bddbce64d3a",
                 "succeeded", "succeeded", "media 首轮被视觉检查阻断、旧版重试 ValidationError；修复（icon 规范化/箭头可见性/审查提示尊重简化示意）后重试成功，已人工抽帧核验"),
    "da4f7f24": ("火山是怎么形成的？", "da4f7f24-6735-4000-8c0f-0c0b3e5b5b1e",
                 "succeeded", "succeeded", "直通完成"),
    "27b03413": ("为什么飞机能飞起来？", "27b03413-6c6c-48a3-bf6a-49f773cf6682",
                 "blocked", "succeeded", "run 证据审核阻断，人工确认后直接制片"),
    "7f9891ff": ("为什么0不能作为除数？", "7f9891ff-2d1b-4f7e-a3a9-c957551a8d93",
                 "succeeded", "succeeded", "直通完成"),
    "f3a924ff": ("为什么打哈欠会传染？", "f3a924ff-a047-4589-85ea-cdfc8f1ee35c",
                 "blocked", "succeeded", "最终打包 EXE 上验证：run 证据审核阻断，人工确认后直接制片"),
}
EXTRA = [  # first EXE-build run of the yawning topic, superseded by f3a924ff
    {"topic": "为什么打哈欠会传染？", "project_id": "2472e34f-5d46-42ea-950b-b606a2bb426d",
     "run_outcome": "blocked", "media_outcome": "succeeded",
     "note": "第一轮 EXE 验证（修复前构建），被 f3a924ff 最终构建结果取代",
     "state": "passed", "duration_seconds": 68.0,
     "probe": {"duration_seconds": 68.0, "resolution": "1280x720", "fps": 20.0,
               "has_video_stream": True, "has_audio_stream": True}},
]


def ffmpeg() -> str:
    sys.path.insert(0, str(ROOT / "backend"))
    import imageio_ffmpeg
    exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not exe.is_file():
        raise SystemExit("FFmpeg runtime missing")
    return str(exe)


def probe(path: Path, exe: str) -> dict:
    info = subprocess.run([exe, "-i", str(path)], capture_output=True, text=True,
                          errors="replace").stderr
    duration = None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", info)
    if m:
        hh, mm, ss = map(float, m.groups())
        duration = hh * 3600 + mm * 60 + ss
    m = re.search(r"(\d{3,4})x(\d{3,4})", info)
    resolution = f"{m.group(1)}x{m.group(2)}" if m else None
    m = re.search(r"(\d+(?:\.\d+)?) fps", info)
    fps = float(m.group(1)) if m else None
    lines = info.splitlines()
    return {"duration_seconds": duration, "resolution": resolution, "fps": fps,
            "has_video_stream": any(l.strip().startswith("Stream") and "Video:" in l for l in lines),
            "has_audio_stream": any(l.strip().startswith("Stream") and "Audio:" in l for l in lines)}


def frames(path: Path, out_dir: Path, exe: str, duration: float) -> list[dict]:
    result = []
    for index, fraction in enumerate((0.1, 0.5, 0.9), start=1):
        target = out_dir / f"frame-{index}.png"
        at = max(0.0, min(duration - 0.05, duration * fraction))
        r = subprocess.run([exe, "-y", "-ss", f"{at:.2f}", "-i", str(path),
                            "-frames:v", "1", str(target)],
                           capture_output=True, text=True, errors="replace")
        result.append({"index": index, "at_seconds": round(at, 2),
                       "ok": r.returncode == 0 and target.is_file() and target.stat().st_size > 0,
                       "bytes": target.stat().st_size if target.is_file() else 0})
    return result


def main() -> None:
    exe = ffmpeg()
    results = []
    for prefix, (topic, project_id, run_outcome, media_outcome, note) in CASES.items():
        case_dir = EVIDENCE / prefix
        mp4 = case_dir / "preview.mp4"
        if not mp4.is_file():
            raise SystemExit(f"missing artifact for {prefix}")
        probe_info = probe(mp4, exe)
        duration = probe_info["duration_seconds"] or 0.0
        frame_list = frames(mp4, case_dir, exe, duration)
        state = "passed" if (probe_info["has_video_stream"] and probe_info["has_audio_stream"]
                             and duration and all(f["ok"] for f in frame_list)) else "partial"
        results.append({
            "topic": topic, "project_id": project_id, "state": state,
            "run_outcome": run_outcome, "media_outcome": media_outcome, "note": note,
            "duration_seconds": duration, "resolution": probe_info["resolution"],
            "fps": probe_info["fps"], "probe": probe_info, "frames": frame_list,
            "video_bytes": mp4.stat().st_size,
        })
    results.extend(EXTRA)
    summary = {
        "created_at": datetime.now().astimezone().isoformat(),
        "merged_from": "scripts/merge_case_evidence.py 合并各次运行记录与产物重探测",
        "cases": len(CASES), "passed": sum(1 for r in results if r["state"] == "passed"),
        "records": len(results),
        "results": results,
    }
    (EVIDENCE / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"merged {len(results)} records; {summary['passed']}/{summary['cases']} cases passed")
    for r in results:
        print(f"- {r['topic']} [{r['project_id'][:8]}] state={r['state']} "
              f"run={r['run_outcome']} media={r['media_outcome']} "
              f"dur={r['duration_seconds']}s {r['probe']['resolution']}")


if __name__ == "__main__":
    main()
