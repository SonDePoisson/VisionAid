# Avancement

| Phase | Statut | Tests | Durée | Notes |
|---|---|---|---|---|
| 0 — Socle | ✅ | 6 passés (unit + data) | ~25 min | open3d épinglé à 0.19 (libusb manquant pour 0.20) |
| 1 — Sources & intrinsèques | ✅ | 12 nouveaux (unit + data) | ~15 min | rotation vérifiée contre l'autorotation ffmpeg |
| 2 — Bus temps réel | ✅ | 14 nouveaux (unit) | ~20 min | HWM relevé à 10 000 (1000 messages en rafale saturaient HWM=1000) |
| 3 — Détection & ReID | ✅ | 11 unit + 8 slow/data | ~1 h | YOLOE-26s-seg + DINOv2-small ; seuil 0,575 ; rappel aug. 98 %, FPR 0 % ; cible confirmée 60 % des frames ; bug de saut de piste corrigé |
| 4 — Profondeur métrique | ✅ | 6 unit + 3 slow/data | ~20 min | DAv2-Metric-Indoor-Small (DA3 indisponible) ; 7,4 img/s ; hauteur gourde 0,33 m vs 0,25 m |
| 5 — Pose (odométrie RGB-D) | ✅ | 7 unit + 3 slow/data | ~45 min | 0 % perdu, 35 keyframes, aller-retour 0,6 % ; critère « par paire » sur keyframes (voir DECISIONS) ; hauteur caméra testée en phase 6 |
| 6 — Fusion 3D | ✅ | 11 unit + 3 slow/data | ~50 min | facteur d'échelle 0,76 ; caméra 1,39 m (σ 8 cm) ; gourde σ 7,5 cm à 0,87 m du sol ; costmap 27 % libre / 73 % occupé (pièce meublée) |
| 7 — Planification | ✅ | 9 unit | ~30 min | A*/D* Lite en numba (2,9 ms / 1,9 ms incrémental sur 200×200) |
| 8 — Logique de guidage | ✅ | 14 unit | ~20 min | priorités, hystérésis 0,15 m, maintien 0,3 s, messages ≥ 3 s |
| 9 — Audio binaural | ✅ | 8 unit | ~25 min | ITD Woodworth, ILD Brown-Duda, indice arrière, sans clic ni écrêtage |
| 10 — Simulateur | ✅ | 8 unit + 1 slow (100 graines × 3) | ~2 h | succès 95/94/96 %, sans collision 96/96/99 %, ratio médian ≈ 0,94 ; carte réelle non navigable (informatif) |
