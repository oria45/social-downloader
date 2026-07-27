# PyInstaller spec for the standalone Windows desktop build.
# Run from backend/: pyinstaller social-downloader.spec
#
# Expects, relative to this file, to already exist before building:
#   ../frontend/dist/   - built frontend (npm run build)
#   tools/               - yt-dlp.exe, gallery-dl.exe, ffmpeg.exe, ffprobe.exe
# Both are populated by .github/workflows/build-windows-exe.yml before this
# spec runs - see that workflow for exact download steps.

a = Analysis(
    ["app/desktop_entry.py"],
    pathex=["."],
    datas=[
        ("../frontend/dist", "frontend_dist"),
        ("tools", "tools"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "slowapi",
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="social-downloader",
    console=True,
)

COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="social-downloader",
)
