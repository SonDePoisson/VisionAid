"""Test de fumée de l'application empaquetée : elle démarre, le guidage (processus séparés)
se lance avec des modèles factices et un faux téléphone, puis elle se ferme proprement.

    python packaging/smoke_test.py dist/VisionAId/VisionAId          # Linux
    python packaging/smoke_test.py dist/VisionAId.app/Contents/MacOS/VisionAId
    python packaging/smoke_test.py dist\\VisionAId\\VisionAId.exe

Aucune dépendance hors bibliothèque standard : lancé avec n'importe quel Python.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_state(base: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base}/api/state", timeout=3) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 - pas encore prêt
        return None


def main(exe: str, timeout: float = 240.0) -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    home = tempfile.mkdtemp(prefix="visionaid-smoke-")
    env = dict(os.environ, VISIONAID_HOME=home)
    print("+", exe, "--self-test", flush=True)
    if subprocess.run([exe, "--self-test"], env=env, timeout=600).returncode != 0:
        log = os.path.join(home, "logs", "visionaid.log")
        if os.path.exists(log):
            print(open(log, encoding="utf-8", errors="replace").read()[-8000:])
        print("ÉCHEC de l'auto-test")
        return 1
    cmd = [exe, "--no-open", "--stub-models", "--fake-phone", "--skip-prepare", "--port", str(port)]
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, env=env)
    ok = False
    last: dict | None = None
    try:
        t_end = time.time() + timeout
        while time.time() < t_end:
            if proc.poll() is not None:
                print(f"l'application s'est arrêtée (code {proc.returncode})")
                break
            st = get_state(base)
            if st:
                last = st
                if st.get("engine") == "error":
                    print("erreur du guidage :", st.get("engine_error"))
                    break
                if st.get("engine") == "ready" and (st.get("phone") or {}).get("connected"):
                    ok = True
                    break
            time.sleep(1)
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            page = r.read().decode("utf-8", "replace")
            ok = ok and "VisionAId" in page
    except Exception as e:  # noqa: BLE001
        print("échec :", e)
        ok = False
    finally:
        try:
            req = urllib.request.Request(
                f"{base}/api/action",
                data=b'{"name": "quit"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(60)
        except subprocess.TimeoutExpired:
            print("pas d'arrêt propre en 60 s : arrêt forcé")
            proc.kill()
            ok = False
    if not ok:
        print("dernier état :", json.dumps(last, ensure_ascii=False)[:2000] if last else None)
        log = os.path.join(home, "logs", "visionaid.log")
        if os.path.exists(log):
            print("---- journal ----")
            print(open(log, encoding="utf-8", errors="replace").read()[-6000:])
    print("OK" if ok else "ÉCHEC", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
