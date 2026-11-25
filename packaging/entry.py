"""Point d'entrée de l'application empaquetée (PyInstaller).

Différences avec `visionaid` lancé depuis les sources :
- `multiprocessing.freeze_support()` : le guidage et la préparation des modèles lancent des
  processus « spawn » ; dans l'exécutable figé, ce sont des copies de ce programme qu'il faut
  rediriger vers le bon code au lieu de relancer l'application.
- les caches écrits par les bibliothèques (numba, Hugging Face, torch, Ultralytics) vont dans le
  dossier de l'utilisateur : le dossier de l'application est en lecture seule (surtout sur Mac).
"""

from __future__ import annotations

import multiprocessing
import os
import sys


def _setup_frozen_env() -> None:
    from visionaid.utils.config import user_dir

    home = user_dir()
    cache = home / ".cache"
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache / "numba"))
    os.environ.setdefault("YOLO_CONFIG_DIR", str(cache / "ultralytics"))
    os.environ.setdefault("MPLCONFIGDIR", str(cache / "matplotlib"))
    os.environ.setdefault("MPLBACKEND", "Agg")  # pas de Tk dans l'application
    # Ultralytics ne doit pas tenter de `pip install` dans l'exécutable figé
    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
    home.mkdir(parents=True, exist_ok=True)
    for d in ("numba", "ultralytics", "matplotlib"):
        (cache / d).mkdir(parents=True, exist_ok=True)
    # Sans console (Windows, Mac lancé depuis le Finder), stdout/stderr valent None : le journal
    # va dans un fichier, utile en cas de problème.
    if sys.stdout is None or sys.stderr is None:
        logs = home / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        fh = open(logs / "visionaid.log", "a", buffering=1, encoding="utf-8")  # noqa: SIM115
        if sys.stdout is None:
            sys.stdout = fh
        if sys.stderr is None:
            sys.stderr = fh
    # Lancé depuis le Finder / le menu Démarrer : le répertoire courant peut être « / »
    try:
        os.chdir(home)
    except OSError:
        pass


def self_test() -> int:
    """`--self-test` : charge chaque bibliothèque lourde comme le fera l'application (sans
    télécharger de modèle). Sert à vérifier l'exécutable figé (CI, packaging/smoke_test.py)."""
    import importlib
    import traceback

    import numpy as np

    def numba_kernels() -> None:
        from visionaid.audio.binaural import spatialize
        from visionaid.planning.astar import warmup

        warmup()
        spatialize(np.zeros(4800, dtype=np.float32), np.zeros(4800), 48000)

    def yolo() -> None:
        from ultralytics import YOLO  # noqa: F401
        from ultralytics.utils import AUTOINSTALL

        assert not AUTOINSTALL, "Ultralytics ne doit pas installer de paquets"

    def hf() -> None:
        from transformers import (  # noqa: F401
            AutoModel,
            AutoModelForDepthEstimation,
            CLIPModel,
            CLIPTokenizer,
            pipeline,
        )

    checks = {
        "torch": lambda: importlib.import_module("torch").zeros(2).sum(),
        "cv2": lambda: importlib.import_module("cv2"),
        "numba": numba_kernels,
        "ultralytics": yolo,
        "transformers": hf,
        "pocket_tts": lambda: importlib.import_module("pocket_tts"),
        "webview": lambda: importlib.import_module("webview"),
        "zeroconf": lambda: importlib.import_module("zeroconf"),
        "ressources": lambda: importlib.import_module("visionaid.utils.config").load_raw(),
        "graphe": lambda: importlib.import_module("visionaid.apps.live_blocks"),
    }
    failed = 0
    for name, fn in checks.items():
        try:
            fn()
            print(f"[ok]     {name}", flush=True)
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"[ÉCHEC]  {name}\n{traceback.format_exc()}", flush=True)
    print("auto-test :", "OK" if not failed else f"{failed} échec(s)", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if getattr(sys, "frozen", False):
        _setup_frozen_env()
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(self_test())
    from visionaid.app.__main__ import main

    raise SystemExit(main())
