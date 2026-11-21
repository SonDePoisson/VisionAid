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
| 11 — Intégration | ✅ (latence ⚠️) | 1 unit/integration (stubs) + 5 slow | ~1 h 15 | offline 485 frames en 72 s, ARRIVED à 0,23 m, cohérence guidage 7° (médiane) ; temps réel 30 s OK, p95 ≈ 450-650 ms > 300 ms |
| 12 — Optimisations | ⚠️ partiel | — | ~15 min | export CoreML testé, non retenu (écart de score 5,8 %, plus lent) ; DA3-Small et graphe de poses non faits |
| 13 — Rapport final | ✅ | night_run : 107 rapides + 23 lents verts, offline et temps réel OK | ~20 min | REPORT.md, captures dans docs/report/ |

## Phase 2 du projet : du téléphone au chemin (`PLAN_PHASE2.md`)

| Phase | Statut | Tests | Durée | Notes |
|---|---|---|---|---|
| 14 — Socle phase 2 | ✅ | 6 unit | ~20 min | messages `ImuSample`, `ImuBatch`, `ClockSync`, `Frame.t_phone/t_recv` ; config `phone`, `body`, `session` ; `docs/protocol.md` |
| 15 — Serveur, page web, faux téléphone | ✅ (page à valider sur iPhone) | 8 unit + 5 integration | ~1 h 15 | HTTPS avec autorité locale, WebSocket JPEG + IMU, acquittement après ingestion, horloge par ping/pong apparié, sessions enregistrées ; page web vérifiée en syntaxe et servie, pas encore testée sur un vrai téléphone |
| 16 — Rejeu de sessions | ✅ | 7 unit + 2 integration + 1 data (skip) | ~40 min | `SessionSource`, `SessionImu`, `open_media` (vidéo ou session) branché sur l'offline, les caches perception/profondeur et le temps réel (`SessionReplayBlock`) ; `apps/session_info.py` |
| ⏸ Checkpoint | en attente de données | — | — | procédure dans `docs/checkpoint_enregistrements.md` ; les phases 17 à 20 continuent sur données synthétiques |
| 17 — Calibration caméra et capteurs | ✅ (synthétique) / ⏸ données réelles | 9 unit + 2 data (skip) | ~1 h | damier synthétique : K à < 2 % ; IMU synthétique : décalage à < 5 ms, biais à < 10 %, rotation à < 2°, erreur d'unités détectée ; chargement automatique par appareil (`config/calib/`) |
| 18 — Pose fusionnée (VIO) | ✅ (synthétique) / ⏸ données réelles | 9 unit + 2 data/slow (skip) | ~1 h 15 | verticale < 2° (marche simulée), rotations rapides avec flou : 0 % `lost` contre 55 % en VO seule, coupure de 1 s : orientation < 3°, échelle de profondeur recalée à < 5 % par la hauteur caméra ; VIO choisie automatiquement quand l'IMU est présente (offline, temps réel) |
| 19 — Prompt fixe et cibles multiples | ✅ (gourde) / ⏸ clés réelles | 19 unit + 1 integration + 1 data/slow (skip) | ~50 min | fiches `config/targets/{gourde,cles}.yaml`, phrase → fiche par mots porteurs (sans modèle de langage), ReID sans couleur ou en texte seul si aucune photo ; gourde inchangée (8 tests lents de la phase 3 verts) ; `--target` sur run_offline, run_realtime, run_phone, calibrate_reid |
