# -*- mode: python ; coding: utf-8 -*-
# Spécification PyInstaller de l'application VisionAId (dossier autonome, pas un fichier unique :
# démarrage plus rapide et compatible avec la signature macOS).
#
#   uv run pyinstaller packaging/visionaid.spec --noconfirm   # → dist/VisionAId(.app)
#
# Préférer `uv run python packaging/build.py`, qui prépare les icônes et fabrique aussi
# l'installateur (.dmg, .exe, .AppImage).
import os
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    get_package_paths,
)

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - défini par PyInstaller
PKG = ROOT / "src" / "visionaid"
ICONS = Path(os.environ.get("VISIONAID_ICONS", ROOT / "packaging" / "build" / "icons"))
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
APP = "VisionAId"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

datas = [
    # ressources lues via `visionaid.utils.config.RESOURCES` (= visionaid/_data hors du dépôt)
    (str(ROOT / "config"), "visionaid/_data/config"),
    (str(ROOT / "assets" / "sounds" / "processed"), "visionaid/_data/assets/sounds/processed"),
    # pages de l'ordinateur et du téléphone
    (str(PKG / "app" / "web"), "visionaid/app/web"),
    (str(PKG / "phone" / "web"), "visionaid/phone/web"),
]
binaries = []
# tout le code de VisionAId : beaucoup d'imports sont faits à la demande ou dans des processus
hiddenimports = collect_submodules("visionaid")

# Bibliothèques qui chargent des fichiers de données ou des modules à la demande
for name in ("ultralytics", "pocket_tts", "webview", "zeroconf", "qrcode"):
    try:
        d, b, h = collect_all(name)
    except Exception as e:  # noqa: BLE001 - paquet absent sur cette plateforme
        print(f"[visionaid.spec] {name} ignoré : {e}")
        continue
    datas += d
    binaries += b
    hiddenimports += h
# Rerun (vue 3D, réglage avancé) : le module Python et son visualiseur
for name in ("rerun", "rerun_bindings", "rerun_cli"):
    try:
        d, b, h = collect_all(name)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:  # noqa: BLE001
        pass
datas += collect_data_files("transformers", include_py_files=False)
# torchvision ≥ 0.2x : extensions `_C_stable` / `image_stable` (chargées par chemin, inconnues du
# hook PyInstaller) — sans elles, `torchvision::nms` manque et transformers ne se charge pas
binaries += collect_dynamic_libs("torchvision")
_tv = Path(get_package_paths("torchvision")[1])
binaries += [
    (str(f), str(Path("torchvision") / f.parent.relative_to(_tv)))
    for ext in ("*.so", "*.pyd", "*.dll", "*.dylib")
    for f in _tv.rglob(ext)
]
# Windows : roues « réparées » par delvewheel (sentencepiece, …) qui rangent leurs DLL dans un
# dossier voisin `<paquet>.libs` que leur __init__ ajoute au chemin de recherche des DLL
_site = _tv.parent
for libs in _site.glob("*.libs"):
    binaries += [(str(f), libs.name) for f in libs.iterdir() if f.is_file()]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # open3d : seulement pour `pose.method: open3d` (hors guidage, ~1 Go) ; le reste : outils de dev
    excludes=["open3d", "pytest", "IPython", "jupyter", "notebook", "tkinter", "PyQt5", "PySide2"],
    # numba (cache=True) a besoin des fichiers .py à côté du bytecode
    module_collection_mode={"visionaid": "pyz+py", "torch": "pyz+py", "ultralytics": "pyz+py"},
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

icon = None
if IS_MAC and (ICONS / "icon.icns").exists():
    icon = str(ICONS / "icon.icns")
elif IS_WIN and (ICONS / "icon.ico").exists():
    icon = str(ICONS / "icon.ico")

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP,
    debug=False,
    strip=False,
    upx=False,
    # Windows / Mac : pas de fenêtre de terminal ; Linux : garder la console (journal visible)
    console=not (IS_MAC or IS_WIN),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=os.environ.get("VISIONAID_TARGET_ARCH") or None,
    codesign_identity=os.environ.get("MACOS_CODESIGN_IDENTITY") or None,
    entitlements_file=str(ROOT / "packaging" / "macos" / "entitlements.plist") if IS_MAC else None,
    icon=icon,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP,
)

if IS_MAC:
    app = BUNDLE(  # noqa: F821
        coll,
        name=f"{APP}.app",
        icon=icon,
        bundle_identifier="fr.visionaid.app",
        version=VERSION,
        info_plist={
            "CFBundleName": APP,
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
            # le téléphone se connecte à l'ordinateur sur le réseau local (visionaid.local)
            "NSLocalNetworkUsageDescription": (
                "VisionAId reçoit l'image et les mouvements du téléphone sur le réseau local."
            ),
            "NSBonjourServices": ["_https._tcp", "_http._tcp"],
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
