"""Build the Windows desktop release: PyInstaller one-directory bundle of the
FastAPI backend + web frontend, launched by scripts/desktop_main.py inside an
embedded WebView2 window (no browser needed).

Output:
  dist/科学科普视频工作台/科学科普视频工作台.exe   double-click to run
  dist/科学科普视频工作台/.env.example             rename to .env and fill key
  dist/科学科普视频工作台/使用说明.txt

Usage: backend/.venv/Scripts/python.exe scripts/build_desktop.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
SPEC = ROOT / "scivis_desktop.spec"
DISTPATH = ROOT / "dist-desktop"  # fresh folder per build; avoids locked-folder cleanup
APP_DIR = DISTPATH / "科学科普视频工作台"


def main() -> None:
    frontend_dist = ROOT / "frontend" / "dist"
    if not (frontend_dist / "index.html").exists():
        raise SystemExit("frontend/dist missing; run `npm ci && npm run build` in frontend first.")
    for module in ("PyInstaller", "webview"):
        try:
            __import__(module)
        except ImportError:
            raise SystemExit(f"{module} not installed in backend/.venv; run: "
                             f"backend/.venv/Scripts/python.exe -m pip install pyinstaller pywebview") from None

    subprocess.run([str(VENV_PY), "-m", "PyInstaller", "--noconfirm",
                    "--distpath", str(DISTPATH), "--workpath", str(ROOT / "build"),
                    str(SPEC)], cwd=ROOT, check=True)

    exe = APP_DIR / "科学科普视频工作台.exe"
    if not exe.is_file():
        raise SystemExit("PyInstaller finished but the expected EXE is missing: " + str(exe))

    # Ship configuration template and user guide next to the executable.
    shutil.copy2(ROOT / ".env.example", APP_DIR / ".env.example")
    guide = APP_DIR / "使用说明.txt"
    guide.write_text(
        "科学科普视频智能体（桌面版）\n"
        "==============================\n"
        "双击“科学科普视频工作台.exe”即可打开使用，无需浏览器。\n"
        "\n"
        "首次使用：\n"
        "1. 把本文件夹中的 .env.example 重命名为 .env；\n"
        "2. 用记事本打开 .env，把 DASHSCOPE_API_KEY= 后面换成你的百炼 API 密钥，\n"
        "   并把 MOCK_AI=true 改为 MOCK_AI=false；\n"
        "3. 重新双击 exe 打开。\n"
        "\n"
        "数据保存在本文件夹 scivis-data 中（问题、视频、音频和字幕），\n"
        "请勿放在只读目录（如 Program Files）；请勿把 .env 和 scivis-data 分享给他人。\n"
        "\n"
        "常见问题：\n"
        "- 启动时弹出检查未通过：按提示处理（缺密钥/目录只读等）。\n"
        "- 如果本机没有 WebView2 运行库，会自动改用默认浏览器打开。\n",
        encoding="utf-8")

    # Zip for distribution (env template only, never a real key).
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = DISTPATH / f"科学科普视频工作台-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                package.write(path, "科学科普视频工作台/" + path.relative_to(APP_DIR).as_posix())
    size_mb = archive.stat().st_size / 1024 / 1024
    print(json_manifest(archive, size_mb))


def json_manifest(archive: Path, size_mb: float) -> str:
    import json
    from hashlib import sha256
    return json.dumps({
        "app_dir": str(APP_DIR),
        "zip": str(archive),
        "zip_bytes": archive.stat().st_size,
        "zip_mb": round(size_mb, 1),
        "zip_sha256": sha256(archive.read_bytes()).hexdigest(),
        "note": "Desktop build; double-click the EXE. .env.example only - real key lives in the user's own .env.",
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
