"""Launch the production frontend + API on one loopback port; never install or kill blindly."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8000"


def healthy():
    try:
        with urlopen(URL + "/api/health", timeout=1) as response:
            health = json.load(response)
        if health.get("service") != "science-poster-agent" or health.get("version") != "0.2.0":
            return False
        if health.get("instance") != sha256(str(ROOT).lower().encode()).hexdigest()[:16]:
            return False
        with urlopen(URL + "/api/studio/presets", timeout=1) as response:
            return isinstance(json.load(response), list)
    except (URLError, OSError, ValueError):
        return False


def main():
    global URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Use a local port between 1024 and 65535")
    URL = f"http://127.0.0.1:{args.port}"
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit("Frontend build missing. Run npm ci and npm run build in frontend first.")
    if not healthy():
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", args.port)) == 0:
                raise SystemExit(f"Port {args.port} is occupied by an older/different service. Stop that service before retrying. No process was killed.")
        print("Starting local app (first run may take a few seconds)...", flush=True)
        logs = ROOT / ".local-logs"
        logs.mkdir(exist_ok=True)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        with (logs / "packaged.out.log").open("ab") as out, (logs / "packaged.err.log").open("ab") as err:
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "backend"),
                "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT / "backend", env=env, stdout=out, stderr=err,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        (logs / "packaged-process.json").write_text(json.dumps({"pid": process.pid, "root": str(ROOT), "started": time.time()}), encoding="utf-8")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit("Startup failed; inspect .local-logs/packaged.err.log (do not share secrets).")
            if healthy():
                break
            time.sleep(0.3)
        else:
            raise SystemExit("Still starting. Check logs and retry; a running service will be reused, not duplicated.")
    print("Ready: " + URL, flush=True)
    if not args.no_browser:
        webbrowser.open(URL)


if __name__ == "__main__": main()
