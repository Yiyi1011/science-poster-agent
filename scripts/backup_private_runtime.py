"""Create a local-only runtime snapshot for handoff and rollback.

The archive intentionally excludes .env and logs. It can contain private project
inputs and model evidence, so it must never be committed or uploaded publicly.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def add_tree(package: zipfile.ZipFile, source: Path, archive_root: str, skip: set[Path]) -> int:
    count = 0
    if not source.exists():
        return count
    for path in source.rglob("*"):
        if path.is_file() and path.resolve() not in skip:
            package.write(path, f"{archive_root}/{path.relative_to(source).as_posix()}")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT.parent / "代码版本备份" / "私有运行数据")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = args.output_root.resolve() / f"scivis-runtime-{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    archive = folder / f"scivis-private-runtime-{stamp}.zip"
    database = ROOT / "artifacts" / "studio.sqlite3"
    file_count = 0
    with tempfile.TemporaryDirectory(prefix="scivis-db-snapshot-") as temporary:
        snapshot = Path(temporary) / "studio.sqlite3"
        if database.exists():
            with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
                target.commit()
            with closing(sqlite3.connect(snapshot)) as check:
                result = check.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("SQLite snapshot integrity check failed")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as package:
            skip = {database.resolve()} if database.exists() else set()
            file_count += add_tree(package, ROOT / "artifacts", "science-poster-agent-private/artifacts", skip)
            file_count += add_tree(package, ROOT / "evidence", "science-poster-agent-private/evidence", set())
            if snapshot.exists():
                package.write(snapshot, "science-poster-agent-private/artifacts/studio.sqlite3")
                file_count += 1
            package.writestr("science-poster-agent-private/README-PRIVATE.txt",
                "PRIVATE LOCAL BACKUP. May contain project inputs, media and model evidence.\n"
                "It contains no .env by design. Do not commit or upload it publicly.\n"
                "Restore into a new directory first; verify before replacing active data.\n")
            file_count += 1
    manifest = {
        "created": datetime.now().astimezone().isoformat(),
        "source_root": str(ROOT),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "archive": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": digest(archive),
        "files": file_count,
        "sqlite_integrity": "ok" if database.exists() else "not_present",
        "contains_env": False,
        "classification": "private-local-only",
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"folder": str(folder), **manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
