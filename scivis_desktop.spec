# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one directory, GUI entry (no console) for the
cross-topic science video desktop app. The executable starts FastAPI on a
local port and opens the app in an embedded WebView2 window via
scripts/desktop_main.py."""
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

datas = [
    # Studio presets JSON is loaded from Path(__file__).parent / "data".
    ("backend/app/data", "app/data"),
    # Bundled web build fallback; a frontend/dist next to the EXE wins at runtime.
    ("frontend/dist", "frontend/dist"),
]

binaries = []
hiddenimports = []

for package in ("uvicorn", "webview", "imageio_ffmpeg", "httpx", "truststore"):
    try:
        data, binary, hidden = collect_all(package)
    except Exception:
        continue
    datas += data
    binaries += binary
    hiddenimports += hidden

# imageio_ffmpeg ships the static ffmpeg binary as package data; make sure it
# lands next to the Python package even if the generic hook misses it.
binaries += collect_dynamic_libs("imageio_ffmpeg")

a = Analysis(
    ["scripts/desktop_main.py"],
    pathex=["backend"],  # resolves against the spec's directory (repo root)
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "app.main",
        "app.studio_routes",
        "app.storyboard_routes",
        "app.services.studio_store",
        "app.services.studio_pipeline",
        "app.services.studio_media",
        "app.services.studio_video",
        "app.services.studio_cartoon",
        "app.services.studio_research",
        "app.services.studio_export",
        "app.services.studio_fallback",
        "app.services.studio_structured_output",
        "app.services.qwen_client",
        "app.services.qwen_image_client",
        "app.services.qwen_tts_client",
        "app.services.qwen_vision_reviewer",
        "app.services.bailian_app_client",
        "app.services.usage_ledger",
        "app.services.model_policy",
        "app.services.pipeline",
        "app.services.svg_renderer",
        "app.services.visual_workflow",
        "app.models",
        "app.studio_models",
        "app.config",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_asyncio", "ipython", "tkinter", "matplotlib", "numpy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="科学科普视频工作台",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="科学科普视频工作台",
)
