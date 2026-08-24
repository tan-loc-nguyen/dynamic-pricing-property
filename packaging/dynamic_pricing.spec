# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the single-binary desktop build.

Build it with `make bundle` from the repository root, which exports the web app
first — this spec bundles `apps/web/out` and fails loudly if it is missing,
because a binary that ships without the frontend starts up and then serves
nothing.

PyInstaller cannot cross-compile: it embeds a native Python interpreter, so a
Windows .exe must be built on Windows and a macOS binary on macOS. The GitHub
Actions matrix in .github/workflows/release.yml does both.
"""

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent
WEB_DIST = REPO_ROOT / "apps" / "web" / "out"

if not WEB_DIST.is_dir():
    raise SystemExit(
        f"The web app has not been exported to {WEB_DIST}.\n"
        "Run `make bundle` from the repository root, which builds it first."
    )

# uvicorn resolves these at RUNTIME through its "auto" indirection, so static
# analysis never sees them and the frozen binary dies on the first request with
# an ImportError that names a module the source code does not mention.
HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

a = Analysis(
    [str(REPO_ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(REPO_ROOT / "apps" / "api")],
    binaries=[],
    # Mounted by dynamic_pricing.packaging.web_dist() at bundle_root()/"web".
    datas=[(str(WEB_DIST), "web")],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The test suite and the linter are in requirements.txt alongside the
    # runtime deps; there is no reason to ship them to an operator.
    excludes=["pytest", "ruff", "_pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DynamicPricingProperty",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # A console, deliberately. It shows the address and the data directory, and
    # closing it is how an operator stops the app — a windowed build gives them
    # no feedback and no way to quit short of Task Manager.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
