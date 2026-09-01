"""Build a local release from committed tracked sources + built web assets. No live data."""
from datetime import datetime
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.5.6-preview")
    parser.add_argument("--channel", choices=["process", "final"], default="process")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", args.version):
        raise SystemExit("Invalid version name")
    tag = f"{args.channel}/v{args.version}"
    tags = subprocess.check_output(["git", "tag", "--points-at", "HEAD"], cwd=ROOT).decode().splitlines()
    if tag not in tags:
        raise SystemExit("Create the verified matching tag first: " + tag)
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([__import__('sys').executable, str(ROOT / 'scripts/audit_repository.py')], cwd=ROOT, check=True)
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    build = ROOT / "frontend/dist"
    if not (build / 'index.html').exists(): raise SystemExit("Run frontend production build first")
    channel_name = "制作过程版" if args.channel == "process" else "最终交付版"
    folder = ROOT.parent / "代码版本备份" / channel_name / f"scivis-v{args.version}-{datetime.now():%Y%m%d-%H%M%S}"
    folder.mkdir(parents=True, exist_ok=False)
    archive = folder / f"scivis-v{args.version}-local.zip"
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for name in filter(None, names): package.write(ROOT / name, 'science-poster-agent/' + name)
        for path in build.rglob('*'):
            if path.is_file(): package.write(path, 'science-poster-agent/' + path.relative_to(ROOT).as_posix())
    bundle = folder / f"scivis-history-v{args.version}.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=ROOT, check=True)
    subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=ROOT, check=True)
    manifest = {"created":datetime.now().astimezone().isoformat(), "channel":args.channel, "tag":tag, "commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip(),
                "files": {p.name: {"bytes":p.stat().st_size,"sha256":sha256(p.read_bytes()).hexdigest()} for p in [archive,bundle]},
                "note":"Prebuilt frontend and source, not a standalone EXE; Python dependencies must be installed. No .env, project database or private evidence. Single-worker local deployment only."}
    (folder / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({"folder":str(folder),**manifest},ensure_ascii=False))


if __name__ == '__main__': main()
