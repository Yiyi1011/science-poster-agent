"""Build a local release from committed tracked sources + built web assets. No live data."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([__import__('sys').executable, str(ROOT / 'scripts/audit_repository.py')], cwd=ROOT, check=True)
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    build = ROOT / "frontend/dist"
    if not (build / 'index.html').exists(): raise SystemExit("Run frontend production build first")
    folder = ROOT.parent / "代码版本备份" / f"scivis-v0.2.0-{datetime.now():%Y%m%d-%H%M%S}"
    folder.mkdir(parents=True, exist_ok=False)
    archive = folder / "scivis-v0.2.0-local.zip"
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for name in filter(None, names): package.write(ROOT / name, 'science-poster-agent/' + name)
        for path in build.rglob('*'):
            if path.is_file(): package.write(path, 'science-poster-agent/' + path.relative_to(ROOT).as_posix())
    bundle = folder / "scivis-history-v0.2.0.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=ROOT, check=True)
    subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=ROOT, check=True)
    manifest = {"created":datetime.now().astimezone().isoformat(), "commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip(),
                "files": {p.name: {"bytes":p.stat().st_size,"sha256":sha256(p.read_bytes()).hexdigest()} for p in [archive,bundle]},
                "note":"Prebuilt frontend and source, not a standalone EXE; Python dependencies must be installed. No .env, project database or private evidence. Single-worker local deployment only."}
    (folder / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({"folder":str(folder),**manifest},ensure_ascii=False))


if __name__ == '__main__': main()
