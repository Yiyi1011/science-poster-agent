"""Desktop launcher: starts the FastAPI server on a local port and opens the
app in a native embedded window (pywebview / WebView2), so users never need a
browser. Falls back to the default browser only if the embedded window cannot
start. Works both inside the PyInstaller build (sys.frozen) and in the dev
repository.

Layout next to the executable (or this script in dev):
  .env                optional; API key lives here, never inside the build
  frontend/dist/      optional; production web build served by FastAPI
  scivis-data/        created automatically; SQLite, media, audio, subtitles
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

APP_VERSION = "0.5.6-preview"
DEFAULT_PORT = 8765
WINDOW_TITLE = "跨主题科普视频智能体"


def app_dir() -> Path:
    """Directory that holds .env / frontend/dist / scivis-data."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("No free local port available")


def load_dotenv_file(path: Path) -> dict[str, str]:
    """Parse a minimal .env file; duplicate of the semantics in app.config."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def preflight(base: Path, env: dict[str, str]) -> list[str]:
    """Return a list of readable problems; empty means everything is ready."""
    problems = []
    for module in ("uvicorn", "fastapi", "PIL", "imageio_ffmpeg", "truststore"):
        try:
            __import__(module)
        except ImportError:
            problems.append(f"缺少运行组件 {module}")
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        if not Path(get_ffmpeg_exe()).is_file():
            problems.append("缺少视频合成组件 FFmpeg")
    except ImportError:
        problems.append("缺少视频合成组件 FFmpeg")
    fonts = [os.getenv("SCIVIS_FONT_PATH", "").strip(), "C:/Windows/Fonts/msyh.ttc",
             "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"]
    if not any(path and Path(path).is_file() for path in fonts):
        problems.append("缺少中文字体（微软雅黑/Noto CJK），视频字幕无法生成")
    data_dir = Path(env.get("SCIENCE_POSTER_DATA_DIR", base / "scivis-data")).expanduser()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".scivis-write-test"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
    except OSError:
        problems.append(f"数据目录不可写：{data_dir}")
    if not env.get("DASHSCOPE_API_KEY"):
        problems.append("未检测到 API 密钥：请在程序旁的 .env 文件填写 DASHSCOPE_API_KEY 才能生成真实视频")
    return problems


def message_box(title: str, text: str) -> None:
    """Native blocking dialog; no extra dependencies on Windows."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
    else:
        print(f"\n[{title}] {text}", flush=True)


_DEBUG_LOG = None


def debug_log(line: str) -> None:
    """Append a milestone line to desktop-debug.log next to the app."""
    global _DEBUG_LOG
    try:
        if _DEBUG_LOG is None:
            _DEBUG_LOG = app_dir() / "desktop-debug.log"
        with _DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now():%H:%M:%S}] {line}\n")
    except Exception:
        pass


def healthy(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            health = json.load(response)
        if health.get("service") != "science-poster-agent" or health.get("version") != APP_VERSION:
            return False
        with urlopen(f"http://127.0.0.1:{port}/api/studio/presets", timeout=1) as response:
            return isinstance(json.load(response), list)
    except (URLError, OSError, ValueError):
        return False


def run_server(port: int) -> tuple[threading.Thread, object]:
    """Start uvicorn on the given port in a background thread; return thread + server."""
    import uvicorn
    sys.path.insert(0, str(app_dir() / "backend"))
    from app.main import app as fastapi_app

    server = uvicorn.Server(uvicorn.Config(fastapi_app, host="127.0.0.1", port=port,
                                           log_level="warning", access_log=False))

    def serve() -> None:
        asyncio.run(server.serve())

    thread = threading.Thread(target=serve, name="scivis-server", daemon=True)
    thread.start()
    return thread, server


def redirect_std_streams(base: Path) -> None:
    """Windowed (console=False) PyInstaller apps have None std streams; any
    print/log write crashes. Point them at a UTF-8 log file next to the app."""
    if sys.stdout is not None:
        return
    try:
        log_file = base / "desktop-run.log"
        handle = log_file.open("a", encoding="utf-8", buffering=1)
        sys.stdout = handle
        sys.stderr = handle
    except Exception:
        pass  # never take the app down over logging


def main() -> int:
    import multiprocessing
    multiprocessing.freeze_support()

    no_window = "--no-window" in sys.argv[1:]  # automated QA: server only
    redirect_std_streams(app_dir())

    base = app_dir()
    debug_log(f"launcher start base={base} frozen={getattr(sys, 'frozen', False)}")
    env = load_dotenv_file(base / ".env")
    for key, value in env.items():
        os.environ.setdefault(key, value)

    # Local writable data + optional frontend bundle must be resolved before
    # any app code imports, because the frozen paths differ from the repo.
    frozen = getattr(sys, "frozen", False)
    if frozen:
        data_dir = os.getenv("SCIENCE_POSTER_DATA_DIR", "").strip() or str(base / "scivis-data")
        os.environ.setdefault("SCIENCE_POSTER_DATA_DIR", data_dir)
        if (base / "frontend" / "dist" / "index.html").exists():
            os.environ.setdefault("SCIVIS_FRONTEND_DIST", str(base / "frontend" / "dist"))
        if (base / ".env").exists():
            os.environ.setdefault("SCIVIS_ENV_FILE", str(base / ".env"))
    # Bundled fallback inside the PyInstaller payload (onedir _internal).
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and (Path(meipass) / "frontend" / "dist" / "index.html").exists():
        os.environ.setdefault("SCIVIS_FRONTEND_DIST", str(Path(meipass) / "frontend" / "dist"))

    debug_log("preflight start")
    problems = preflight(base, env)
    debug_log(f"preflight problems: {len(problems)} -> " + "; ".join(problems))
    if problems:
        try:
            (base / "启动检查问题.txt").write_text(
                "以下问题需要处理：\n" + "\n".join("- " + p for p in problems)
                + "\n\n修正后重新打开程序。", encoding="utf-8")
        except Exception:
            pass
        message_box("启动检查未通过",
                    "以下问题需要处理：\n\n" + "\n".join("- " + p for p in problems)
                    + "\n\n修正后重新打开程序。")
        return 1

    port = find_free_port(DEFAULT_PORT)
    debug_log(f"port={port} starting server thread")
    thread, server = run_server(port)
    url = f"http://127.0.0.1:{port}"

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not thread.is_alive():
            debug_log("server thread died before ready")
            message_box("启动失败", "服务未能启动，请查看程序旁的 desktop-debug.log 后重试。")
            return 1
        if healthy(port):
            debug_log("server healthy")
            break
        time.sleep(0.3)
    else:
        debug_log("server health timeout")
        message_box("启动超时", "服务启动超时，请重试。")
        server.should_exit = True
        return 1

    if no_window:
        print(f"Ready: {url}", flush=True)
        try:
            while True:
                time.sleep(1)
                if not thread.is_alive():
                    break
        except KeyboardInterrupt:
            pass
        server.should_exit = True
        thread.join(timeout=10)
        return 0

    window = None
    try:
        import webview  # native embedded window (WebView2 on Windows)
        window = webview.create_window(WINDOW_TITLE, url, width=1440, height=920,
                                       min_size=(1024, 700))
        webview.start()
    except Exception as exc:
        # Embedded window unavailable: degrade to the default browser.
        message_box("提示", f"嵌入式窗口不可用（{type(exc).__name__}），将打开默认浏览器。")
        import webbrowser
        webbrowser.open(url)
        message_box(WINDOW_TITLE, "已打开浏览器，使用结束后点击“确定”关闭应用。")

    server.should_exit = True
    if window is None:
        thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
