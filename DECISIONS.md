# Journal des décisions

Format : date — contexte — choix — alternative écartée.

- **2026-11-21 — Données d'entrée** — Les fichiers fournis sont `assets/IMG_0270.MOV` (HEVC 1920×1080, rotation 90°, 16,2 s, 30 fps) et deux photos HEIC. Copie du flux vidéo sans ré-encodage vers `data/video/appart.mp4` (métadonnée de rotation conservée, pour exercer la gestion de rotation) et conversion des HEIC en `data/ref/gourde_{1,2}.jpg` via `sips`. — Alternative écartée : ré-encoder en H.264 en appliquant la rotation (perte de qualité et le test de rotation devenait trivial).
- **2026-11-21 — Version de Python** — Le dépôt initial impose Python 3.12 (`.python-version`, `requires-python>=3.12`). On garde 3.12 au lieu du 3.11 du plan : toutes les dépendances sont disponibles. — Alternative écartée : rétrograder vers 3.11 (aucun bénéfice).
- **2026-11-21 — open3d** — open3d 0.20 (wheel macOS arm64) dépend de `/opt/homebrew/opt/libusb` absent ; installer via Homebrew sort du périmètre réseau autorisé. 2ᵉ tentative : open3d 0.19 qui fonctionne. Contrainte `open3d<0.20`. numpy forcé en 2.x (pyarrow, requis par rerun, exige numpy ≥ 2).
- **2026-11-21 — Config en dataclasses** — Les dataclasses de config sont générées dynamiquement à partir du YAML (`dataclasses.make_dataclass`), accès par attribut `cfg.section.cle`. — Alternative écartée : écrire à la main ~20 dataclasses dupliquant le YAML (risque de désynchronisation).
