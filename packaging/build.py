"""Fabrique l'application installable de VisionAId pour le système courant.

    uv run python packaging/build.py            # exécutable + installateur
    uv run python packaging/build.py --no-installer

Résultat dans `dist/` :
- macOS   : VisionAId.app et VisionAId-<version>-macos-<arch>.dmg
- Windows : VisionAId\\ et VisionAId-<version>-windows-x64-setup.exe (+ .zip portable)
- Linux   : VisionAId/ et VisionAId-<version>-linux-x86_64.AppImage (+ .tar.gz)

Les modèles (~2,6 Go) ne sont pas embarqués : l'application les télécharge au premier lancement.
Signature macOS facultative (variables d'environnement) : MACOS_CODESIGN_IDENTITY, puis pour la
notarisation APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "packaging"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP = "VisionAId"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "aarch64"}.get(m, m)


def make_icons() -> Path:
    out = PACK / "build" / "icons"
    run([sys.executable, PACK / "make_icons.py", out])
    return out


def pyinstaller(icons: Path) -> None:
    env = dict(os.environ, VISIONAID_ICONS=str(icons))
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            PACK / "visionaid.spec",
            "--noconfirm",
            "--distpath",
            DIST,
            "--workpath",
            BUILD / "pyinstaller",
        ],
        env=env,
        cwd=ROOT,
    )


# ------------------------------------------------------------------------------------- macOS
def package_macos() -> Path:
    app = DIST / f"{APP}.app"
    _maybe_sign_and_notarize(app)
    dmg = DIST / f"{APP}-{VERSION}-macos-{arch()}.dmg"
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    run(["ditto", app, stage / app.name])  # ditto garde liens et attributs étendus
    run(["ditto", build_macos_uninstaller(), stage / UNINSTALLER_MAC])
    (stage / "Applications").symlink_to("/Applications")
    dmg.unlink(missing_ok=True)
    run(
        [
            "hdiutil",
            "create",
            "-volname",
            APP,
            "-srcfolder",
            stage,
            "-ov",
            "-format",
            "UDZO",
            "-imagekey",
            "zlib-level=9",
            dmg,
        ]
    )
    if os.environ.get("MACOS_CODESIGN_IDENTITY"):
        run(["codesign", "--force", "--sign", os.environ["MACOS_CODESIGN_IDENTITY"], dmg])
        _notarize(dmg)
    return dmg


UNINSTALLER_MAC = f"Désinstaller {APP}.app"


def build_macos_uninstaller() -> Path:
    """Petite application AppleScript « Désinstaller VisionAId », livrée dans le .dmg."""
    out = DIST / UNINSTALLER_MAC
    shutil.rmtree(out, ignore_errors=True)
    run(["osacompile", "-o", out, PACK / "macos" / "uninstall.applescript"])
    icns = PACK / "build" / "icons" / "icon.icns"
    if icns.exists():
        shutil.copy(icns, out / "Contents" / "Resources" / "applet.icns")
    ident = os.environ.get("MACOS_CODESIGN_IDENTITY")
    if ident:  # Developer ID : runtime renforcé + horodatage, exigés par la notarisation
        run(["codesign", "--force", "--options", "runtime", "--timestamp", "--sign", ident, out])
    else:  # signature ad hoc
        run(["codesign", "--force", "--sign", "-", out])
    return out


def _maybe_sign_and_notarize(app: Path) -> None:
    ident = os.environ.get("MACOS_CODESIGN_IDENTITY")
    if not ident:
        # signature « ad hoc » (déjà faite par PyInstaller) : l'application s'ouvre après
        # clic droit → Ouvrir, ou `xattr -dr com.apple.quarantine /Applications/VisionAId.app`
        print("Pas de MACOS_CODESIGN_IDENTITY : application non signée (ad hoc).")
        return
    run(
        [
            "codesign",
            "--force",
            "--deep",
            "--options",
            "runtime",
            "--timestamp",
            "--entitlements",
            PACK / "macos" / "entitlements.plist",
            "--sign",
            ident,
            app,
        ]
    )
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])


def _notarize(path: Path) -> None:
    need = ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_APP_PASSWORD")
    if not all(os.environ.get(k) for k in need):
        print("Pas d'identifiants Apple : notarisation ignorée.")
        return
    run(
        [
            "xcrun",
            "notarytool",
            "submit",
            path,
            "--apple-id",
            os.environ["APPLE_ID"],
            "--team-id",
            os.environ["APPLE_TEAM_ID"],
            "--password",
            os.environ["APPLE_APP_PASSWORD"],
            "--wait",
        ]
    )
    run(["xcrun", "stapler", "staple", path])


# ----------------------------------------------------------------------------------- Windows
def package_windows() -> list[Path]:
    out: list[Path] = []
    zip_base = DIST / f"{APP}-{VERSION}-windows-x64-portable"
    shutil.make_archive(str(zip_base), "zip", DIST, APP)
    # version portable : pas de désinstalleur Windows, un script à double-cliquer à la place
    with zipfile.ZipFile(zip_base.with_suffix(".zip"), "a") as zf:
        bat = (PACK / "windows" / "desinstaller.bat").read_text(encoding="utf-8")
        zf.writestr(f"{APP}/Désinstaller {APP}.bat", bat.replace("\n", "\r\n"))
    out.append(zip_base.with_suffix(".zip"))
    iscc = shutil.which("iscc") or shutil.which("ISCC")
    for cand in (
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ):
        if not iscc and Path(cand).exists():
            iscc = cand
    if not iscc:
        print("Inno Setup (ISCC) introuvable : seul le .zip portable est produit.")
        return out
    run(
        [
            iscc,
            f"/DAppVersion={VERSION}",
            f"/DSourceDir={DIST / APP}",
            f"/DOutputDir={DIST}",
            f"/DIconFile={PACK / 'build' / 'icons' / 'icon.ico'}",
            PACK / "windows" / "visionaid.iss",
        ]
    )
    out.append(DIST / f"{APP}-{VERSION}-windows-x64-setup.exe")
    return out


# ------------------------------------------------------------------------------------- Linux
def package_linux(icons: Path) -> list[Path]:
    out: list[Path] = []
    tgz = DIST / f"{APP}-{VERSION}-linux-{arch()}.tar.gz"
    with tarfile.open(tgz, "w:gz", compresslevel=6) as tf:
        tf.add(DIST / APP, arcname=APP)
    out.append(tgz)

    appdir = BUILD / f"{APP}.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    (appdir / "usr" / "lib").mkdir(parents=True)
    shutil.copytree(DIST / APP, appdir / "usr" / "lib" / APP, symlinks=True)
    shutil.copy(PACK / "linux" / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    shutil.copy(PACK / "linux" / "visionaid.desktop", appdir / "visionaid.desktop")
    shutil.copy(icons / "icon-512.png", appdir / "visionaid.png")
    icodir = appdir / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
    icodir.mkdir(parents=True)
    shutil.copy(icons / "icon-512.png", icodir / "visionaid.png")

    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not tool:
        print("appimagetool introuvable : seul le .tar.gz est produit.")
        return out
    image = DIST / f"{APP}-{VERSION}-linux-{arch()}.AppImage"
    env = dict(os.environ, ARCH=platform.machine(), APPIMAGE_EXTRACT_AND_RUN="1")
    run([tool, "--no-appstream", appdir, image], env=env)
    out.append(image)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-installer", action="store_true", help="exécutable seulement")
    ap.add_argument("--skip-pyinstaller", action="store_true", help="réutiliser dist/")
    args = ap.parse_args()

    icons = make_icons()
    if not args.skip_pyinstaller:
        pyinstaller(icons)
    if args.no_installer:
        return 0
    if sys.platform == "darwin":
        outs = [package_macos()]
    elif sys.platform.startswith("win"):
        outs = package_windows()
    else:
        outs = package_linux(icons)
    print("\nFichiers produits :")
    for p in outs:
        if p.exists():
            print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size / 1e6:.0f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
