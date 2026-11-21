# VisionAId — Plan d'implémentation pour Claude Code (exécution autonome)

> **Mode d'exécution : autonome, de bout en bout, sans validation intermédiaire.**
> Tu implémentes toutes les phases dans l'ordre, sans t'arrêter pour demander mon avis.
> Chaque phase se termine par des tests automatiques verts (ou marqués `xfail` avec justification), un commit, puis tu passes à la suivante.
> Je lis `PROGRESS.md`, `DECISIONS.md` et `REPORT.md` le matin.

---

## 0. Contexte

### Objectif produit
Guider une personne malvoyante jusqu'à un objet détecté en temps réel dans une pièce, à partir d'un flux vidéo monoculaire. Le guidage est sonore et binaural. Il évite les obstacles et recalcule le chemin en continu.

### Ce qu'on construit cette nuit
Tout le pipeline sur Mac M4 (Apple Silicon, PyTorch MPS), alimenté par **une vidéo enregistrée** et lue comme un flux temps réel (*replay*). Le streaming depuis le téléphone (WebRTC + pose ARKit) viendra plus tard. L'architecture doit le permettre sans refonte, via les interfaces `FrameSource` et `PoseSource`.

### Données d'entrée (fournies par moi)
- `data/video/appart.mp4` : vidéo de mon appartement filmée au téléphone (monoculaire, pas de LiDAR, pas d'IMU dans le fichier).
- `data/ref/gourde_*.jpg` : une ou plusieurs photos de l'objet cible, **une gourde grise et orange**.
- L'objet cible apparaît dans la vidéo.

Si un fichier manque : les tests qui en dépendent sont `skip` avec un message clair, et tu continues avec les tests synthétiques. Tu ne bloques jamais.

### Sorties attendues au matin
- `outputs/annotated.mp4` : vidéo annotée (détection, objet ancré, costmap en vignette, chemin, flèche de guidage, état).
- `outputs/session.rrd` : enregistrement Rerun complet (images, profondeur, nuage de points, trajectoire, costmap, chemin, cible).
- `outputs/guidance.wav` : piste audio binaurale synchronisée avec la vidéo.
- `outputs/report.json` : métriques chiffrées.
- `REPORT.md` : bilan lisible (ce qui marche, chiffres, échecs, prochaines étapes).

---

## 1. Règles d'autonomie (à respecter strictement)

1. **Ne jamais attendre d'entrée humaine.** Aucune commande interactive, aucune question. En cas d'ambiguïté, choisis l'option la plus simple qui marche et consigne-la dans `DECISIONS.md` (date, contexte, choix, alternative écartée).
2. **Suivre l'ordre des phases.** Une phase est terminée quand ses tests passent : `pytest -m "not slow"` vert, puis les tests `slow` de la phase.
3. **Commit git après chaque phase**, message `phase N: <résumé>`. Le dossier `data/` et les poids de modèles sont dans `.gitignore`.
4. **Mettre à jour `PROGRESS.md`** à chaque fin de phase : statut (✅ / ⚠️ partiel / ❌), tests, durée, problèmes.
5. **Time-box de ~90 min par phase.** Au-delà, marque la phase ⚠️, mets les tests bloquants en `pytest.mark.xfail(reason=...)` avec une raison précise, et passe à la suivante. Les phases suivantes doivent rester exécutables grâce aux fallbacks.
6. **Ne jamais supprimer un test ni affaiblir un seuil en silence.** Tout changement de seuil est justifié dans `DECISIONS.md`.
7. **Dépendances : 2 tentatives d'installation maximum**, puis bascule sur le fallback listé et consignation.
8. **Timeouts obligatoires** : `pytest-timeout`, 120 s par défaut, 1800 s pour les tests marqués `slow`. Aucun processus ne doit pouvoir pendre toute la nuit. Les sous-processus du bus ont un timeout et sont tués proprement en fin de test.
9. **Réseau** : uniquement `pip`/`uv`, Hugging Face et les téléchargements de poids Ultralytics.
10. **Ne pas faire tourner les gros modèles à chaque test unitaire.** Les tests unitaires utilisent des données synthétiques ou des stubs. Les modèles réels vont dans des tests marqués `slow`, avec mise en cache des sorties (`.cache/`) pour les réexécutions.

---

## 2. Conventions de code

- Python 3.11, gestion d'environnement avec `uv` (fallback `venv` + `pip`).
- **N'utilise jamais `super()`.** Préfère la composition, les `Protocol` (typing) et les `dataclass`. Si un héritage est inévitable (par ex. `torch.nn.Module`), appelle explicitement `ParentClass.__init__(self, ...)`.
- Type hints partout, `ruff` pour le lint et le format, docstrings courtes en français.
- Toute la configuration est dans `config/default.yaml`, chargée en dataclasses. Aucun nombre magique dans le code.
- Conventions géométriques, à documenter dans `docs/frames.md` :
  - repère caméra OpenCV : x à droite, y vers le bas, z vers l'avant ;
  - repère monde : origine à la première pose, **z vers le haut** après alignement sur le sol (voir phase 6) ;
  - poses en matrices 4×4 `T_world_cam` (float64) ;
  - unités en mètres, secondes et radians.
- Chaque message porte un `t` (timestamp en secondes, horloge de la source) et un `frame_idx`.
- Device torch : `mps` si disponible, sinon `cpu`. Détection centralisée dans `visionaid/utils/device.py`.

### Arborescence cible
```
visionaid/
  pyproject.toml
  Makefile                      # setup, test-fast, test-all, run-offline, run-realtime, night
  config/default.yaml
  data/                         # gitignored : video/, ref/
  outputs/                      # gitignored
  docs/frames.md
  src/visionaid/
    utils/      device.py, config.py, timing.py, logging.py
    io/         sources.py (FrameSource, VideoFileSource, ReplaySource, WebRTCSource stub)
                intrinsics.py
    bus/        messages.py, transport.py (ZeroMQ), nodes.py, runner.py
    perception/ detector.py, reid.py, tracker.py, depth.py
    pose/       source.py (PoseSource, VisualOdometry, ArkitPoseSource stub), vo.py
    mapping/    geometry.py, floor.py, costmap.py, object_anchor.py
    planning/   astar.py, dstar_lite.py, lookahead.py
    guidance/   state_machine.py, cues.py
    audio/      binaural.py, renderer.py
    sim/        world.py, agent.py, scenarios.py
    viz/        rerun_logger.py, overlay.py
    apps/       run_offline.py, run_realtime.py, calibrate_reid.py, inspect_data.py
  tests/
    conftest.py                 # fixtures synthétiques, chemins data, markers
    unit/  data/  integration/
  scripts/night_run.sh
  PROGRESS.md  DECISIONS.md  REPORT.md
```

### Markers pytest
- `unit` : rapides, synthétiques, sans modèle ni données réelles.
- `data` : nécessitent la vidéo ou les photos (`skip` si absentes).
- `slow` : chargent un vrai modèle (détection, profondeur, ré-identification).
- `integration` : pipeline complet.

---

## 3. Phases

Chaque phase donne l'objectif, les livrables, les tests et la définition de « terminé ».

### Phase 0 — Socle du projet
**Livrables**
- `pyproject.toml` avec les dépendances : numpy, opencv-python, torch, torchvision, transformers, ultralytics, open3d, pyzmq, msgpack, msgpack-numpy, rerun-sdk, soundfile, scipy, pyyaml, pytest, pytest-timeout, ruff.
- Config, logging, `device.py`, `Makefile`, `.gitignore`, `PROGRESS.md`, `DECISIONS.md`.
- `apps/inspect_data.py` : affiche les métadonnées de la vidéo (résolution, fps, durée, **rotation**) et de chaque photo de référence, et sauvegarde 10 frames échantillonnées dans `outputs/inspect/`.

**Tests**
- `unit` : chargement de la config, sélection du device.
- `data` : la vidéo s'ouvre, fps > 0, au moins 1 photo de référence lisible.

**Terminé quand** `make test-fast` est vert.

---

### Phase 1 — Sources d'images et intrinsèques
**Livrables**
- `FrameSource` (Protocol) : `read() -> Frame | None`, `intrinsics`, `fps`.
- `VideoFileSource` :
  - gère la rotation (métadonnées) ;
  - redimensionne à une largeur configurable (défaut 640 px) ;
  - fournit des timestamps issus de la vidéo.
- `ReplaySource` : enveloppe une source fichier et la débite **au rythme réel**. Si le consommateur est en retard, les frames sont sautées, jamais mises en file d'attente.
- `WebRTCSource` : stub qui lève `NotImplementedError`, avec docstring décrivant le contrat attendu (frames + pose horodatée).
- `intrinsics.py` : K par défaut à partir d'un champ de vision horizontal configurable (défaut 69°, typique d'un grand-angle de smartphone en vidéo). Option `estimate_from_model` si le modèle de profondeur choisi expose des intrinsèques. Option de chargement d'une calibration OpenCV (damier) si fournie.

**Tests**
- `unit` : sur une vidéo synthétique générée dans le test (cv2.VideoWriter, 3 s, motif connu) :
  - nombre de frames ;
  - timestamps strictement croissants ;
  - rotation appliquée correctement ;
  - `ReplaySource` à 1× met environ 3 s (±10 %) ;
  - avec un consommateur lent, `ReplaySource` saute des frames au lieu d'accumuler du retard.
- `unit` : K cohérent (cx, cy au centre, fx > 0).
- `data` : lecture complète de `appart.mp4` sans erreur.

---

### Phase 2 — Bus temps réel
Architecture multi-processus, un nœud par bloc, communication **ZeroMQ pub/sub** sérialisée en msgpack (+ msgpack-numpy).

**Livrables**
- `messages.py` : dataclasses `Frame`, `Pose`, `Depth`, `Detections`, `ObjectEstimate`, `Costmap`, `Path`, `GuidanceCue`, avec (dé)sérialisation.
- `transport.py` :
  - `Publisher` et `Subscriber` ;
  - option **« dernière valeur seulement »** (`ZMQ_CONFLATE` ou drain non bloquant) pour les flux lourds (images, profondeur) ;
  - file normale pour les flux légers.
- `nodes.py` : nœud générique (boucle, cadence cible, mesure de latence, arrêt propre sur signal).
- `runner.py` : lance et arrête un graphe de nœuds décrit dans la config.
- Mode **mono-processus** équivalent, qui appelle les blocs en séquence sur chaque frame. Il sert au mode offline déterministe et aux tests. Les deux modes partagent exactement le même code métier.

**Tests**
- `unit` :
  - aller-retour de sérialisation pour chaque message (avec tableaux numpy) ;
  - pub/sub local : 1000 messages légers reçus dans l'ordre ;
  - en mode conflate, un abonné lent ne reçoit que des messages récents (âge < 2 périodes) ;
  - latence médiane locale < 5 ms pour une image 640×480 ;
  - arrêt du runner < 2 s sans processus zombie.

---

### Phase 3 — Détection et ré-identification de la gourde
Le point clé : **retrouver *cette* gourde grise et orange, pas n'importe quelle bouteille.**

**Livrables**
- `detector.py` : détecteur open-vocabulary **YOLOE** (dernière génération disponible dans Ultralytics, idéalement YOLOE-26, variante segmentation, petite taille).
  - Prompt texte configurable, par défaut `["water bottle", "bottle", "flask"]`.
  - **Prompt visuel** à partir des photos de référence, si l'API le permet.
  - Sorties : boîtes, masques, scores.
  - Fallbacks dans l'ordre : YOLOE-11 → YOLO-World v2 → YOLO26/YOLO11 COCO classe `bottle`. Consigner le choix.
- `reid.py` : embedding des crops masqués avec **DINOv2-small** (transformers). Fallback : CLIP/MobileCLIP via open_clip.
  - Galerie construite à partir des photos de référence et de leurs augmentations.
  - Score = similarité cosinus maximale avec la galerie, combinée à un **score couleur** : histogramme HSV, proportions de gris et d'orange dans le masque.
  - Pondération configurable.
- `apps/calibrate_reid.py` : calcule le seuil de décision.
  - Positifs : augmentations des photos de référence (rotation, échelle, flou, luminosité, recadrage partiel, occultation 30 %).
  - Négatifs : crops d'autres objets détectés dans la vidéo (prompt large `["cup","bottle","chair","bag","box"]`), en excluant les crops trop similaires à la référence.
  - Seuil choisi pour maximiser F1. Sauvegarde dans `config/reid_threshold.yaml`.
- `tracker.py` : ByteTrack (intégré à Ultralytics, ou implémentation simple IoU + Kalman). La décision « c'est la gourde » est prise **par piste**, avec hystérésis : confirmée après N frames au-dessus du seuil (défaut 3), perdue après M frames sans détection (défaut 10).

**Tests**
- `unit` : avec un détecteur et un encodeur stubs, vérifier la logique de piste et l'hystérésis (confirmation, perte, réacquisition).
- `slow`, `data` :
  - sur chaque photo de référence, la gourde est détectée et ré-identifiée (score ≥ seuil) ;
  - sur 30 augmentations par photo, rappel ≥ 90 % ;
  - sur les négatifs, taux de faux positifs ≤ 5 % ;
  - **robustesse couleur** : sur la photo avec teinte décalée (orange → bleu), le score passe sous le seuil (preuve que la couleur compte).
- `slow`, `data` sur la vidéo :
  - au moins une piste confirmée « gourde » ;
  - fraction des frames où la gourde est confirmée, consignée dans `report.json` (informatif) ;
  - aucune piste confirmée sur un objet dont la teinte dominante est incompatible (contrôle couleur) ;
  - débit de détection mesuré sur MPS, consigné.

---

### Phase 4 — Profondeur métrique
**Livrables**
- `depth.py` avec backends interchangeables (config `depth.backend`) :
  1. **Depth Anything 3 Metric** (`depth-anything/DA3METRIC-LARGE`) pour la qualité ;
  2. **DA3-Small** (relatif) + recalage d'échelle pour la vitesse ;
  3. Fallback : **Depth Anything V2 Metric Indoor Small** via `transformers.pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf")`.

  Consigner le backend retenu et son débit sur M4.
- Sortie : carte de profondeur en mètres à la résolution de l'image, plus une confiance si disponible.
- Lissage temporel optionnel (moyenne exponentielle guidée par la pose, désactivé par défaut).
- Cache disque des profondeurs par frame (`.cache/depth/<hash_video>/<idx>.npz`), pour que les phases suivantes et les réexécutions soient rapides.

**Tests**
- `unit` : avec un backend stub, forme, dtype, valeurs > 0, chemin de cache.
- `slow`, `data` sur 50 frames échantillonnées :
  - profondeur médiane dans [0,3 ; 8] m (intérieur) ;
  - variation relative médiane entre frames consécutives < 15 % ;
  - **contrôle d'échelle avec un objet connu** : la hauteur 3D estimée de la gourde (masque + profondeur + K) est dans ±40 % de `target.height_m` (config, défaut 0,25 m). Si le test échoue, appliquer un facteur d'échelle global estimé sur la gourde, le consigner, et retester.

---

### Phase 5 — Pose 6DoF par odométrie visuelle
La vidéo n'a pas d'IMU. On estime donc la pose par **odométrie RGB-D**, en utilisant la profondeur métrique comme canal D. L'interface doit permettre de brancher plus tard la pose ARKit.

**Livrables**
- `PoseSource` (Protocol) :
  - `VisualOdometry` (implémentation) ;
  - `ArkitPoseSource` (stub documenté).
- `vo.py`, méthode principale :
  - features ORB (OpenCV) + appariement + rétroprojection 3D des points de la frame de référence grâce à la profondeur ;
  - `solvePnPRansac` pour obtenir la transformation ;
  - stratégie de **keyframes** (nouvelle keyframe si translation > 0,15 m, rotation > 10° ou inliers < seuil) ;
  - **score de qualité** par pose (nombre d'inliers, erreur de reprojection).
- Méthode alternative : `open3d.pipelines.odometry.compute_rgbd_odometry`. Activable par config, et utilisée automatiquement si PnP échoue sur une frame.
- Gestion de la perte de suivi : pose marquée `quality=lost`, réinitialisation sur la keyframe suivante. La perte est signalée en aval (le guidage doit le savoir).
- Optionnel, si le temps le permet : petite optimisation de graphe de poses sur les keyframes. Ne pas commencer avant d'avoir terminé les phases 6 à 11.

**Tests**
- `unit`, synthétique :
  - nuage de points 3D aléatoire, trajectoire caméra connue (cercle + translation), projection avec K, bruit de 0,5 px → erreur de translation relative < 3 % et erreur de rotation < 1° par paire ;
  - dérive cumulée sur 100 frames < 5 % de la distance parcourue ;
  - outliers injectés (30 %) : le résultat reste dans les tolérances ;
  - frame sans texture : la pose est `lost`, sans exception.
- `slow`, `data` sur la vidéo :
  - aucun saut > 0,5 m ni > 30° entre deux frames consécutives non `lost` ;
  - fraction de frames `lost` < 10 % (sinon consigner et analyser) ;
  - **hauteur caméra au-dessus du sol** (après la phase 6) entre 0,8 et 1,9 m, écart-type < 0,15 m ;
  - **cohérence aller-retour** : sur un segment de 10 s lu à l'endroit puis à l'envers, l'écart de pose finale est < 10 % de la distance parcourue.

---

### Phase 6 — Fusion 3D : sol, costmap, ancrage de l'objet
**Livrables**
- `geometry.py` : rétroprojection profondeur → nuage de points, changements de repère, sous-échantillonnage (pas de pixel configurable).
- `floor.py` :
  - estimation du plan du sol par RANSAC (Open3D ou numpy) sur les points de la moitié basse de l'image ;
  - définition de l'axe « haut » du monde (z) et de la hauteur caméra ;
  - plan suivi et mis à jour lentement.
- `costmap.py` : grille 2D vue de dessus (résolution 5 cm, taille dynamique) :
  - occupation en **log-odds** ;
  - un point est un obstacle s'il est dans la bande de hauteur [0,05 ; 1,90] m au-dessus du sol, sinon il marque la cellule comme sol libre ;
  - lancer de rayons simplifié pour libérer les cellules entre la caméra et l'obstacle ;
  - **oubli** progressif (décroissance vers l'inconnu) pour gérer les obstacles mobiles ;
  - **gonflage** du rayon du corps (config, 0,35 m) et coût décroissant autour des obstacles, pour préférer les chemins dégagés ;
  - trois états de cellule : libre, occupée, inconnue.
- `object_anchor.py` :
  - position 3D de la gourde = médiane des points 3D sous le masque (ou sous la boîte rétrécie), transformée en repère monde ;
  - filtre de Kalman 3D (ou moyenne exponentielle pondérée par la confiance) ;
  - **mémoire** : la position est conservée quand l'objet sort du champ, avec une incertitude qui croît ;
  - états `unknown` / `seen` / `remembered` / `stale`.

**Tests**
- `unit`, synthétique :
  - sol plan bruité → plan retrouvé (angle < 2°, hauteur < 3 cm) ;
  - boîte de 0,5 m posée au sol → cellules occupées au bon endroit (IoU > 0,8) ;
  - points au plafond (2,3 m) ignorés ;
  - gonflage : distance obstacle → première cellule libre ≈ rayon ± 1 cellule ;
  - décroissance : un obstacle retiré redevient non occupé en N mises à jour ;
  - ancrage : objet vu depuis 5 poses bruitées → position à < 5 cm ; hors champ pendant 3 s → état `remembered`, position conservée.
- `slow`, `data` sur la vidéo :
  - la costmap finale contient des zones libres et occupées non triviales (libre > 20 %, occupé > 2 %) ;
  - écart-type de la position 3D de la gourde sur les frames où elle est confirmée < 0,30 m ;
  - export d'une image PNG de la costmap finale dans `outputs/`.

---

### Phase 7 — Planification de chemin
**Livrables**
- `astar.py` : A* en 8-connexité sur la costmap (coût = distance + coût de proximité).
  - Option : les cellules inconnues ont un coût modéré configurable (approche « optimiste prudente »).
- `dstar_lite.py` : D* Lite incrémental, réutilisé entre les cycles. Il se met à jour quand des cellules changent ou que le départ bouge.
- `lookahead.py` :
  - lissage du chemin (raccourcis en ligne de vue) ;
  - **point d'anticipation** à distance configurable (défaut 1,0 m) sur le chemin. C'est vers lui qu'on guide, pas vers l'objet directement.
- Cible de planification = la cellule libre la plus proche de l'objet (l'objet est souvent sur un meuble, donc dans une cellule « occupée »).

**Tests**
- `unit` :
  - grilles connues, longueur égale à celle de Dijkstra (référence brute) à 1e-6 près ;
  - cible inatteignable → `None`, sans boucle infinie ;
  - D* Lite donne la même longueur que A* recalculé après insertion ou suppression aléatoire d'obstacles (50 scénarios aléatoires) ;
  - performance : grille 200×200, A* < 50 ms et D* Lite incrémental < 10 ms en moyenne ;
  - les chemins restent hors des cellules gonflées ;
  - le point d'anticipation est sur le chemin, à la bonne distance, ou est la cible si le chemin est plus court.

---

### Phase 8 — Logique de guidage
**Livrables**
- `state_machine.py`, états :
  - `SEARCHING` : objet jamais vu → consigne de balayage lent ;
  - `NAVIGATING` : chemin valide → cap vers le point d'anticipation ;
  - `APPROACHING` : à moins de 1,2 m → guidage direct vers l'objet, avec élévation (hauteur du meuble) ;
  - `ARRIVED` : à moins de 0,5 m ;
  - `OBSTACLE_ALERT` : prioritaire, si un obstacle est à moins de 0,6 m dans le cône frontal de ±30° ;
  - `TRACKING_LOST` : pose `lost` → consigne d'arrêt.
- Hystérésis sur toutes les transitions (pas de clignotement d'état).
- `cues.py` : produit un `GuidanceCue` contenant :
  - azimut et élévation relatifs à la tête (pour l'instant tête = caméra ; prévoir un champ `T_cam_head` dans la config, identité par défaut) ;
  - distance, état, niveau d'alerte ;
  - éventuel message vocal court, avec limitation de fréquence (pas plus d'un toutes les 3 s).

**Tests**
- `unit`, pilotés par table : séquences d'entrées (distances, pose perdue, obstacle) → séquences d'états attendues.
  - Pas plus d'un changement d'état par 0,3 s en entrée bruitée.
  - Signe de l'azimut correct : cible à gauche → azimut positif selon la convention documentée.
  - Priorité de l'alerte obstacle sur la navigation.
  - Limitation de fréquence des messages vocaux.

---

### Phase 9 — Rendu audio binaural
**Livrables**
- `binaural.py` :
  - **modèle paramétrique déterministe**, sans téléchargement :
    - ITD de Woodworth (rayon de tête 8,75 cm) ;
    - ILD par filtre d'ombre de la tête dépendant de l'azimut ;
    - indice avant/arrière par filtrage spectral (atténuation des aigus pour l'arrière) ;
  - option : HRTF SOFA (KEMAR) si `sofar` s'installe et que le fichier se télécharge. Sinon, rester sur le modèle paramétrique et le consigner.
- `renderer.py` :
  - balise continue spatialisée sur le point d'anticipation ;
  - cadence des bips en fonction de la distance (plus rapide en s'approchant) ;
  - hauteur tonale en fonction de l'élévation en `APPROACHING` ;
  - son distinct et prioritaire pour `OBSTACLE_ALERT` ;
  - silence + bip d'arrêt pour `TRACKING_LOST` ;
  - jingle court pour `ARRIVED` ;
  - interpolation de l'azimut entre deux cues (pas de saut audible) ;
  - deux modes : écriture WAV synchronisée (offline) et lecture temps réel optionnelle (`sounddevice`, désactivée par défaut et dans les tests).

**Tests**
- `unit` :
  - source à +60° (gauche) → canal gauche **en avance** (lag de corrélation croisée cohérent avec l'ITD théorique ± 0,1 ms) et **plus fort** (ILD > 3 dB) ; symétrique à droite ;
  - source à 0° → canaux quasi identiques ;
  - avant vs arrière à même azimut latéral → énergie haute fréquence plus faible à l'arrière ;
  - pas d'écrêtage (|x| < 1) ;
  - pas de clic : saut d'échantillon maximal borné lors d'un changement d'azimut ;
  - durée du WAV égale à la durée de la session ± 1 frame.

---

### Phase 10 — Simulateur en boucle fermée
Indispensable pour tester le guidage sans utilisateur réel.

**Livrables**
- `sim/world.py` : monde 2D vu de dessus (grille vérité terrain). Générateur de scénarios :
  - pièces rectangulaires avec meubles aléatoires ;
  - couloir avec porte ;
  - obstacle qui apparaît en cours de route ;
  - **carte réelle** = costmap issue de la vidéo (phase 6), si disponible.
- Capteur simulé : costmap partielle construite seulement avec ce que l'agent « voit » (cône de 70°, portée de 4 m, bruit).
- `sim/agent.py` : utilisateur virtuel qui suit le `GuidanceCue` :
  - tourne vers l'azimut avec un délai de réaction (300 ms) et un bruit angulaire (σ = 10°) ;
  - avance à 0,6 m/s, s'arrête sur alerte ou perte de suivi ;
  - en `SEARCHING`, balaye sur place.
- Le simulateur réutilise **exactement** les modules `mapping`, `planning` et `guidance` réels.

**Tests**
- `unit`, avec 100 graines aléatoires par type de scénario :
  - taux de succès (arrivée < 0,5 m de l'objet en < 120 s simulées) ≥ 90 % ;
  - **0 collision** avec la vérité terrain dans ≥ 95 % des runs ;
  - ratio longueur parcourue / chemin optimal ≤ 1,6 (médiane) ;
  - scénario d'obstacle apparu : replanification réussie dans ≥ 90 % des cas.
- Sortie : GIF ou MP4 de 3 runs représentatifs dans `outputs/sim/`, et statistiques dans `report.json`.

---

### Phase 11 — Intégration
**Livrables**
- `viz/rerun_logger.py` : journalise tous les flux, avec timeline = timestamp vidéo. À brancher progressivement dès la phase 3 si possible.
- `viz/overlay.py` : rendu de `annotated.mp4` :
  - boîte et masque de la gourde ;
  - autres détections en gris ;
  - état et distance ;
  - flèche de cap ;
  - mini-costmap avec chemin et position.
- `apps/run_offline.py` :
  - mode mono-processus déterministe sur toute la vidéo ;
  - produit `annotated.mp4`, `session.rrd`, `guidance.wav` (muxé dans une copie `annotated_audio.mp4` via ffmpeg si disponible) et `report.json`.
- `apps/run_realtime.py` :
  - graphe multi-processus sur le bus, `ReplaySource` à 1× ;
  - mesure les latences par étage (p50/p95), le taux de frames sautées et les fréquences effectives ;
  - stratégie multi-cadence : détection à chaque frame disponible, profondeur et pose aussi vite que possible, planification à 5 Hz, cues à 20 Hz.
- **Évaluation de cohérence du guidage sur la vidéo** (informatif, pas bloquant) : pendant les segments où la caméra se rapproche de la gourde, angle entre l'azimut de guidage et la direction réelle de déplacement dans la seconde suivante (médiane, consignée).

**Tests**
- `integration`, `data`, `slow` :
  - `run_offline` va au bout sans exception ;
  - les 4 fichiers de sortie existent et ne sont pas vides ;
  - la gourde est confirmée au moins une fois ;
  - l'état `ARRIVED` ou `APPROACHING` est atteint si la vidéo se termine près de la gourde (distance finale estimée < 1,2 m). Sinon, test informatif.
- `integration`, `data` :
  - `run_realtime` tourne 30 s sans crash et s'arrête proprement ;
  - latence de bout en bout p95 mesurée et consignée. Objectif < 300 ms : si dépassé, consigner les étages fautifs et les pistes d'optimisation (export CoreML de YOLO, DA3-Small, baisse de résolution) sans bloquer.
- `integration`, `unit` : le pipeline complet tourne sur une vidéo synthétique avec stubs (sans modèles), pour vérifier le câblage en < 30 s.

---

### Phase 12 — Optimisations (seulement si tout le reste est ✅ ou ⚠️)
Par ordre de priorité :
1. Export CoreML du détecteur (`model.export(format="coreml")`) et bascule par config. Tests : mêmes détections à ±5 % de score, gain de débit consigné.
2. Profondeur DA3-Small + recalage d'échelle via la gourde ou le sol. Tests de la phase 4 rejoués.
3. Optimisation du graphe de poses sur les keyframes.

---

### Phase 13 — Rapport final
- `scripts/night_run.sh` :
  - lance tous les tests (`pytest -m "not slow"` puis `pytest -m slow`) ;
  - lance `run_offline` puis `run_realtime` (30 s) ;
  - agrège les résultats ;
  - tout est loggé dans `outputs/night_run.log` ;
  - le script est lancé sous `caffeinate -i` s'il est disponible.
- `REPORT.md`, en français :
  - résumé en 10 lignes ;
  - tableau des phases (statut, tests passés/échoués/xfail) ;
  - métriques clés : rappel et faux positifs de la ré-identification, débits par modèle, % de frames `lost`, écart-type de la position de la gourde, succès du simulateur, latences p50/p95 ;
  - captures (costmap PNG, quelques frames annotées) ;
  - décisions importantes (renvoi vers `DECISIONS.md`) ;
  - limites connues et **prochaines étapes**, en particulier :
    - le branchement ARKit (pose) + WebRTC ;
    - l'audio rendu sur le téléphone à partir de la cible en coordonnées monde ;
    - le suivi de tête.

---

## 4. Critères de réussite globaux (par ordre d'importance)
1. Le pipeline offline tourne de bout en bout sur ma vidéo et produit les sorties.
2. La gourde grise et orange est retrouvée et distinguée des autres objets, avec des tests verts sur mes photos.
3. Le simulateur montre un guidage qui atteint l'objet sans collision dans ≥ 90 % des cas.
4. Le mode temps réel tourne en replay avec des latences mesurées.
5. Tout est testé, commité et documenté pour que je puisse reprendre le matin.
