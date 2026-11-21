# VisionAId — Plan phase 2 : du téléphone au chemin, en temps réel

> **Mode d'exécution : autonome, avec un seul point d'arrêt humain (enregistrements sur le téléphone).**
> Ce plan prolonge `PLAN_VISIONAID.md` (phases 0 à 13, terminées). Les règles d'autonomie (§1) et les conventions de code (§2) de ce plan restent valables telles quelles, sauf mention contraire ci-dessous.
> La numérotation des phases continue à partir de 14, pour que les messages de commit `phase N: …` restent uniques.

---

## 0. Contexte

### Objectif de cette étape
Remplacer la vidéo rejouée par **le flux en direct d'un téléphone porté sur le torse**, et faire tourner sur le PC tout le traitement **jusqu'au chemin** :
- acquisition ;
- pose ;
- détection ;
- profondeur ;
- fusion 3D ;
- planification.

**Hors périmètre** :
- le format du guidage, l'audio HRTF et la voix (étape suivante) ;
- les options mémoire, visage et support (post-it du bas du schéma).

### Schéma bloc retenu
```
Téléphone (caméra + gyro + accéléro) ─► transmission tél → PC ─┬─► Détection objet (prompt fixe) ─┐
                                                               ├─► Profondeur ────────────────────┼─► Fusion 3D ─► Chemin
                                                               └─► Pose (VO + gyro + gravité) ────┘
```
Le temps réel est une contrainte transverse : latence mesurée à chaque étage, toujours en mode « dernière valeur seulement ».

### Décisions déjà prises avec l'équipe
- **Téléphone de référence** : iPhone 12, sans LiDAR. Le code vise aussi Android (Chrome), sans le garantir faute d'appareil de test.
- **Acquisition par une page web** servie par le PC en HTTPS et ouverte dans le navigateur du téléphone. Pas d'application native : elle reste en réserve si la pose est trop instable, auquel cas on passerait à ARKit, qui fonctionne sans LiDAR.
- **Pose** : uniquement par la vidéo et les capteurs de base. Le gyroscope donne la rotation, l'accéléromètre la gravité, et l'odométrie visuelle (VO) donne le déplacement.
- **Téléphone fixé sur le torse, en portrait.** On considère que **tête = torse**, avec une transformation caméra → corps fixe.
- **Prompt fixe** choisi au lancement, par exemple « où est ma gourde » ou « où sont mes clés ».
- **Deux boucles à terme** : une boucle lente sur le PC jusqu'au chemin, et une boucle rapide sur le téléphone pour l'audio. Cette étape ne construit que la boucle lente. Les messages doivent cependant déjà permettre la seconde : la cible et le chemin sont exprimés en coordonnées monde.

### Choix de transport (à valider à la relecture)
**Transport principal : WebSocket sécurisé, images JPEG et capteurs horodatés sur la même horloge du téléphone.** WebRTC reste en option (phase 21).

Pourquoi WebSocket plutôt que WebRTC :
- **Horodatage exact.** Chaque image est saisie par la page avec son horodatage `performance.now()`, la même horloge que les événements capteurs. La synchronisation image ↔ IMU est donc directe. Avec WebRTC, il faudrait la reconstruire à partir des horodatages RTP.
- **Pas de tampon de gigue, pas de négociation ICE/mDNS.** La négociation ICE et les adresses mDNS sont une source classique de pannes entre Safari et `aiortc` sur un réseau local.
- **Contre-pression simple.** Le téléphone n'envoie une nouvelle image que lorsque la précédente a été acquittée, donc aucun retard ne peut s'accumuler.
- **Coût acceptable.** En 640×480, une image JPEG à qualité 0,7 pèse environ 40 Ko, soit environ 0,6 Mo/s à 15 images/s, ce qui passe sans problème en Wi-Fi local.

---

## 1. Règles propres à cette étape (en plus du §1 du premier plan)

1. **Point d'arrêt humain unique (§3, « Checkpoint »).** Tant que les enregistrements réels manquent, les tests `data` correspondants sont `skip` avec un message clair, et tu avances sur les données synthétiques et le faux téléphone. Tu ne bloques jamais. Dans `PROGRESS.md`, indique `⏸ en attente de données` pour la partie concernée.
2. **Le faux téléphone fait foi pour l'automatisation.** Un client Python (`tools/fake_phone.py`) parle exactement le même protocole que la page web. Tous les tests de bout en bout passent par lui. La page web, elle, est validée à la main sur l'iPhone, via la checklist du checkpoint.
3. **Réseau.** Comme avant (pip/uv, Hugging Face, poids Ultralytics). **Aucun service externe** pour le certificat, le QR code ou un relais : tout est généré localement.
4. **Vie privée.** Les sessions enregistrées (images de l'appartement) vont dans `data/sessions/`, ignoré par git. Elles ne sont jamais poussées.
5. **Ne pas casser l'existant.** Les 130 tests actuels restent verts à chaque phase. `run_offline` sur `appart.mp4` doit continuer de fonctionner.

---

## 2. Formats et conventions ajoutés

### Repères
À ajouter dans `docs/frames.md` :
- **Repère appareil** (spécification W3C DeviceMotion) : x à droite, y vers le haut de l'écran, z sortant de l'écran, vers l'utilisateur.
- **Caméra arrière en portrait** : la rotation `R_cam_imu` vaut a priori `diag(1, −1, −1)`. Elle est **vérifiée par calibration** (phase 17), car les conventions d'axes et d'unités varient d'un navigateur à l'autre (deg/s ou rad/s).
- **Repère corps** = repère tête (hypothèse tête = torse) : x vers l'avant horizontal, y à gauche, z vers le haut. `T_cam_body` est fixe et donné par la config. L'ancien `T_cam_head` devient un alias de `T_cam_body`.

### Messages
Nouveaux messages dans `bus/messages.py`, sérialisables comme les autres :
- `ImuSample` :
  - `t` : temps téléphone, en s ;
  - `gyro` : rad/s, repère appareil ;
  - `accel` : m/s², gravité incluse ;
  - `accel_lin` : m/s², facultatif ;
  - `orientation` : quaternion, facultatif.
- `ImuBatch` : liste d'`ImuSample`, envoyée toutes les ~50 ms.
- `Frame` gagne les champs `t_phone` (horodatage de saisie sur le téléphone) et `t_recv` (horodatage de réception sur le PC). Les deux sont facultatifs, pour rester compatible avec la vidéo.
- `ClockSync` : décalage estimé entre l'horloge du téléphone et celle du PC, avec son incertitude.

### Protocole WebSocket
Endpoint `wss://<pc>:8443/ws`.
- **Messages binaires** : un en-tête msgpack de longueur fixe préfixée, suivi du JPEG. L'en-tête contient `{type: "frame", seq, t_phone, w, h}`.
- **Messages texte JSON** :
  - `{type: "imu", samples: [...]}` ;
  - `{type: "hello", ua, screen, camera: {w, h, facing}}` ;
  - `{type: "ping", t_phone}` et la réponse `{type: "pong", t_phone, t_pc}` ;
  - `{type: "ack", seq}`, envoyé par le PC vers le téléphone ;
  - `{type: "stats", ...}`, envoyé par le PC vers le téléphone pour l'affichage.
- **Version de protocole** dans `hello`. Le serveur refuse proprement une version inconnue.

### Format de session enregistrée
Dossier `data/sessions/<AAAAMMJJ-HHMMSS>_<nom>/` :
- `frames/` : les JPEG reçus, tels quels, sans recompression ;
- `frames.jsonl` : une ligne par image (`seq`, `t_phone`, `t_recv`, `w`, `h`, `fichier`) ;
- `imu.jsonl` : une ligne par échantillon ;
- `meta.json` : appareil (user agent), version du protocole, synchronisation d'horloge, hauteur caméra déclarée, cible, notes ;
- `video.mp4` : facultatif, généré après coup pour la visualisation (ffmpeg).

---

## 3. Phases

### Phase 14 — Socle de la phase 2
**Livrables**
- Dépendances :
  - `aiohttp`, pour HTTPS, WebSocket et les fichiers statiques ;
  - `cryptography`, pour l'autorité de certification et le certificat locaux ;
  - `qrcode`, pour afficher l'URL dans le terminal.
- Nouveaux messages (§2) et leur sérialisation.
- `docs/frames.md` : ajout des repères (§2).
- `docs/protocol.md` : protocole WebSocket et format de session.
- Nouvelles sections de config :
  - `phone`, avec le port, la résolution demandée, la qualité JPEG, les images/s max et la cadence IMU ;
  - `body`, avec `T_cam_body` et la hauteur caméra déclarée `camera_height_m` (défaut 1,30 m) ;
  - `session`, avec le dossier et l'option d'enregistrement.

**Tests**
- `unit` : aller-retour de sérialisation des nouveaux messages.
- `unit` : un `Frame` sans `t_phone` reste valide, pour la compatibilité.

---

### Phase 15 — Serveur d'acquisition et page web
**Livrables**
- `phone/certs.py` : génère une autorité de certification locale et un certificat serveur couvrant `localhost`, l'IP locale et `<hostname>.local`, dans `.certs/` (ignoré par git).
  - Le serveur expose aussi `http://<pc>:8080/ca.crt`, en HTTP simple, pour installer le profil sur l'iPhone.
  - Procédure d'installation dans `docs/phone_setup.md` : Réglages → Général → VPN et gestion de l'appareil, puis Informations → Réglages des certificats.
- `phone/server.py` (aiohttp) :
  - sert la page web et le WebSocket ;
  - publie sur le bus les `Frame` (JPEG décodé, redimensionné à `video.width`) et les `ImuBatch` ;
  - répond aux `ping` et acquitte chaque image ;
  - enregistre la session si `--record` est passé ;
  - accepte un seul téléphone à la fois et gère proprement la déconnexion et la reconnexion.
- `phone/web/index.html` + `app.js`, en JavaScript pur, sans framework ni CDN :
  - **Démarrage** : un gros bouton « Démarrer » déclenche, dans le même geste, `DeviceMotionEvent.requestPermission()` (iOS) et `getUserMedia` sur la caméra arrière. Le Wake Lock empêche l'écran de se mettre en veille.
  - **Envoi des images** : la page saisit les images à N images/s depuis le `<video>` via un canvas, en JPEG, et ne renvoie une image qu'après l'acquittement de la précédente.
  - **Envoi des capteurs** : les événements `devicemotion` sont regroupés toutes les 50 ms. La page fait un `ping` toutes les secondes.
  - **Affichage** : images/s envoyées, cadence IMU, latence aller-retour, état de la connexion, et le **niveau** (inclinaison du téléphone) pour aider à bien le placer sur le torse.
  - **Mode « calibration »** : envoie des images à pleine résolution, sur demande (bouton « Capturer »).
  - **Compatibilité** : détection des fonctions disponibles, avec repli si la permission n'existe pas (Android) et des messages d'erreur clairs (HTTPS manquant, permission refusée, caméra introuvable).
- `apps/run_phone.py` :
  - lance le serveur ;
  - affiche l'URL et un QR code dans le terminal ;
  - option `--record <nom>`.
- `tools/fake_phone.py` : client Python qui suit le protocole et rejoue une vidéo (ou des images synthétiques) avec une IMU synthétique cohérente. Il accepte un décalage d'horloge, de la gigue et des pertes configurables.

**Tests**
- `unit` : les certificats sont générés et valides pour les noms attendus ; un client TLS qui fait confiance à l'autorité locale se connecte.
- `integration` : faux téléphone → serveur pendant 10 s.
  - Les images reçues sur le bus sont dans l'ordre et aucune n'est en double.
  - La cadence reçue est ≥ 90 % de la cadence envoyée.
  - Avec un consommateur lent, l'âge des images (`t_recv` − envoi) reste < 2 périodes : pas d'accumulation.
- `integration` : coupure puis reconnexion du faux téléphone ; le serveur repart sans redémarrage.
- `integration` : session enregistrée complète et cohérente (nombre d'images, IMU couvrant toute la durée, `meta.json` valide).
- `unit` : une version de protocole inconnue est refusée avec un message.

---

### Phase 16 — Rejeu de sessions
**Livrables**
- `io/session.py` :
  - `SessionSource` (FrameSource) rejoue une session enregistrée **au rythme réel**, avec les sauts d'images comme `ReplaySource` ;
  - `SessionImu` fournit les échantillons IMU compris entre deux images.
- `run_offline` et le graphe temps réel acceptent `--session <dossier>` à la place de la vidéo.
- `apps/session_info.py` : résumé d'une session (durée, images/s réelles, trous, cadence IMU, décalage d'horloge) et génération de `video.mp4` pour la visualisation.

**Tests**
- `unit` : une session synthétique enregistrée par le faux téléphone se rejoue à l'identique (mêmes images, mêmes horodatages).
- `unit` : à chaque image, la fenêtre IMU retournée couvre exactement l'intervalle entre deux images.
- `data` (skip sans session réelle) : chaque session de `data/sessions/` se lit de bout en bout.

---

### ⏸ Checkpoint humain — Enregistrements avec l'iPhone 12
Arrivé ici, tu écris `docs/checkpoint_enregistrements.md`, la procédure à suivre par l'équipe, puis **tu continues** avec les phases 17 à 20 sur les données synthétiques. Les tests `data` restent en `skip` jusqu'à ce que les données arrivent.

**Procédure demandée à l'équipe**
1. **Mise en route** : installer le certificat, ouvrir l'URL, vérifier la checklist de la page (images/s, IMU, latence affichées). Si le Wi-Fi isole les appareils, connecter le PC au partage de connexion de l'iPhone.
2. **Calibration de la caméra** :
   - afficher le damier sur l'écran du PC (`/calib/board`) et mesurer la taille d'une case à la règle ;
   - en mode calibration, capturer 15 à 20 vues sous des angles variés.
3. **Calibration IMU** : téléphone sur le torse,
   - 5 s immobile ;
   - puis 3 rotations lentes sur place (gauche puis droite) ;
   - puis 3 rotations rapides ;
   - puis 5 s immobile.
4. **Sessions de navigation**, téléphone sur le torse, en déclarant la hauteur de la caméra mesurée au sol :
   - `gourde_piece` : partir à 3-4 m de la gourde, la chercher en tournant, puis aller jusqu'à elle ;
   - `cles_piece` : idem avec les clés posées sur un meuble ;
   - `couloir` : traverser un passage avec des obstacles ;
   - `rotations_rapides` : tourner vite sur place, pour tester la robustesse de la pose.
5. **Photos de référence** des clés (5 à 10, fonds variés) dans `data/ref/cles_*.jpg`.
6. **Retour d'expérience** à noter dans la session (`meta.json` → `notes`) : chauffe, coupures, gêne du support.

**Checklist de la page web à valider à la main**
- [ ] HTTPS accepté sans avertissement après installation du certificat.
- [ ] Permission des capteurs et de la caméra obtenue d'un seul geste.
- [ ] L'écran ne se met pas en veille pendant 5 min.
- [ ] Au moins 15 images/s reçues et au moins 50 Hz d'IMU, pendant 5 min, sans dérive de latence.
- [ ] Reconnexion automatique après une coupure du Wi-Fi.

---

### Phase 17 — Calibration caméra et capteurs
**Livrables**
- `apps/calibrate_camera.py` : calibration OpenCV au damier à partir d'une session en mode calibration.
  - Rejet des vues floues ou mal détectées.
  - Sortie : `config/calib/<appareil>_<w>x<h>.yaml`, avec K et la distorsion.
  - Vérification de cohérence avec le champ de vision attendu de l'iPhone 12, consignée.
- `calib/imu_cam.py` : estime automatiquement trois grandeurs à partir d'une session.
  - **Biais du gyroscope** : sur les segments immobiles.
  - **Décalage temporel image ↔ IMU** : il couvre la latence de saisie de la caméra. On l'estime par corrélation croisée entre la norme de la vitesse angulaire du gyroscope et la vitesse de rotation visuelle (homographie ou VO entre images successives).
  - **Rotation `R_cam_imu`** : alignement de Kabsch des vitesses angulaires gyroscope ↔ visuelles. Le résultat est comparé à la valeur a priori, ce qui détecte aussi une erreur d'unités (deg/s au lieu de rad/s).
- Les résultats sont écrits dans `config/calib/<appareil>_imu.yaml` et chargés automatiquement à partir du user agent de la session, avec repli sur les valeurs par défaut.

**Tests**
- `unit` : damier synthétique rendu avec une K connue → K retrouvée à moins de 2 %.
- `unit` : IMU synthétique avec un biais, un décalage de 40 ms et une rotation connus → biais retrouvé à moins de 10 %, décalage à moins de 5 ms, rotation à moins de 2°.
- `unit` : gyroscope en deg/s injecté → erreur d'unités détectée et signalée.
- `data` (skip sans session) : calibration sur les sessions réelles, avec une erreur de reprojection inférieure à 0,5 px, consignée.

---

### Phase 18 — Pose fusionnée (VO + gyroscope + gravité)
**Livrables**
- `pose/imu.py` :
  - intégration du gyroscope entre deux images, corrigée du biais et du décalage ;
  - estimation de la gravité par filtre passe-bas sur l'accéléromètre, robuste à la marche.
- `pose/vio.py` (`VisualInertialOdometry`), qui enveloppe la VO existante :
  - **a priori de rotation** : la rotation intégrée du gyroscope sert d'estimation initiale au PnP et à la prédiction des correspondances, ce qui réduit la recherche et les pertes en rotation rapide ;
  - **gravité** : l'axe z du monde est fixé par l'accéléromètre dès la première seconde. Le sol estimé par RANSAC (phase 6) sert alors de contrôle et ne dicte plus l'axe vertical ;
  - **repli en cas de perte de la VO** : l'orientation continue avec le gyroscope seul, la position est gelée et la qualité passe à `degraded`. L'état `lost` n'est déclaré qu'après N secondes ;
  - **échelle** : la hauteur de caméra déclarée (`body.camera_height_m`) sert de référence. Le facteur d'échelle de la profondeur est ré-estimé en continu par la distance au sol, ce qui remplace le facteur fixe de 0,76 calibré sur l'ancienne vidéo. Il reste borné et lissé.
- `PoseSource` sélectionnable par la config : `vo` (actuel), `vio` (nouveau, défaut pour les sessions téléphone), `arkit` (stub conservé).

**Tests**
- `unit` : séquences synthétiques de la phase 5 enrichies d'une IMU simulée (bruit, biais, décalage) :
  - erreur de verticale < 2° ;
  - en rotation rapide (150°/s), taux d'images `lost` de la VIO ≤ la moitié de celui de la VO seule ;
  - précision de translation au moins égale à celle de la VO seule.
- `unit` : VO coupée artificiellement pendant 1 s → l'orientation reste à moins de 3° de la vérité, la qualité passe à `degraded` puis revient à `ok`.
- `unit` : échelle de profondeur biaisée de 30 % → le facteur de correction converge à moins de 5 % de la vérité grâce à la hauteur caméra.
- `data` (skip sans session) : hauteur caméra estimée à moins de 5 cm de la valeur déclarée ; taux de `lost` sur `rotations_rapides`, VIO contre VO, consigné.

---

### Phase 19 — Prompt fixe et cibles multiples
**Livrables**
- `config/targets/<nom>.yaml` : une fiche par objet cible.
  - Phrases déclenchantes (« où est ma gourde », « où sont mes clés »).
  - Prompts texte pour YOLOE (en anglais).
  - Photos de référence, facultatives.
  - Hauteur réelle, facultative, pour le contrôle d'échelle.
  - Modèle de couleur facultatif. Le score couleur actuel devient propre à chaque fiche ; les clés n'en ont pas, ou en ont un métallique, selon les mesures.
- `perception/target.py` :
  - résolution du prompt fixe vers une fiche, par table de correspondance normalisée (minuscules, accents, articles), sans modèle de langage ;
  - message d'erreur listant les cibles connues si rien ne correspond.
- La ré-identification devient générique.
  - **Avec photos de référence** : galerie DINOv2 et seuil calibré par fiche (`config/reid_threshold_<nom>.yaml`, même procédure qu'en phase 3).
  - **Sans photos** : on se contente de la détection par le texte, avec un seuil de confiance plus strict, et la limite est consignée.
- Option `--target "où sont mes clés"` sur `run_offline`, `run_phone` et le graphe temps réel.

**Tests**
- `unit` : les variantes de formulation (« Où est ma gourde ? », « ma gourde », « gourde ») mènent à la bonne fiche, et une phrase inconnue renvoie une erreur claire.
- `unit` : les fiches sans couleur et sans photos se chargent et le pipeline tourne avec des stubs.
- `data`, `slow` : la gourde reste à au moins 95 % de rappel et 0 % de faux positifs sur les données de la phase 3 (non-régression).
- `data`, `slow` (skip sans photos des clés) : rappel et faux positifs des clés sur `cles_piece`, **informatif**, consigné sans seuil bloquant, car c'est un objet difficile.

---

### Phase 20 — Temps réel du téléphone jusqu'au chemin
**Livrables**
- `apps/run_live.py` : graphe multi-processus.
  ```
  phone_server ─► perception ─┐
               ─► geometry (profondeur + VIO, reçoit Frame + ImuBatch) ─► world ─► planner
  ```
  - Les nœuds `guidance` et `sink` audio sont retirés de ce graphe. Un nœud `path_sink` journalise et mesure.
- **Visualisation en direct** : Rerun en mode viewer, lancé par l'app, avec l'image annotée, la carte, la trajectoire, le chemin, la cible et les latences. Un enregistrement `.rrd` est fait en parallèle.
- **Mesures** :
  - âge des données à chaque étage, à partir de `t_phone` converti en temps PC ;
  - latence de bout en bout `capture → chemin publié` (p50/p95) ;
  - cadences effectives et taux d'images sautées ;
  - écrites dans `outputs/live_report.json`.
- Le même graphe accepte `--session` (rejeu au rythme réel) et `--fake-phone`, pour les tests et la mise au point sans téléphone.
- **Comportements dégradés** :
  - téléphone déconnecté → les nœuds restent vivants, le chemin est marqué invalide, puis tout repart à la reconnexion ;
  - pose perdue → chemin invalide jusqu'à la récupération.

**Tests**
- `integration` : faux téléphone → chemin publié en moins de 60 s après le démarrage (préchauffage des modèles inclus), sur une scène synthétique avec des stubs.
- `integration`, `slow` : faux téléphone rejouant `appart.mp4` avec une IMU synthétique pendant 30 s.
  - Aucun crash, arrêt propre en moins de 2 s.
  - Au moins 2 Hz de chemins valides une fois la gourde confirmée.
  - Latences consignées.
- `integration` : déconnexion et reconnexion du faux téléphone en cours de route → reprise sans redémarrage.
- `data`, `slow` (skip sans session) : rejeu de `gourde_piece` à 1×.
  - La gourde est confirmée.
  - Le chemin est valide au moins une fois.
  - **Objectif de latence capture → chemin p95 < 700 ms**, consigné. Il est plus large qu'en phase 11 car le réseau s'ajoute. Si l'objectif est manqué, consigner les étages fautifs sans bloquer.

---

### Phase 21 — Optimisations (seulement si 14 à 20 sont ✅ ou ⚠️)
Par ordre de priorité :
1. **Profondeur** à résolution réduite (364 px) et sur une image sur N, la pose IMU couvrant les images intermédiaires. Gain de latence et effet sur la précision de la carte consignés.
2. **Costmap incrémentale** : seules les cellules touchées par les nouveaux rayons sont mises à jour.
3. **Transport WebRTC** en option (`aiortc`), uniquement si le WebSocket JPEG se révèle limitant. Les tests de la phase 15 sont rejoués sur ce transport.

---

### Phase 22 — Rapport
- `scripts/night_run.sh` étendu :
  - tests rapides et lents ;
  - `run_live --fake-phone` pendant 30 s ;
  - rejeu de chaque session réelle disponible.
- `REPORT_PHASE2.md`, en français, sur le modèle de `REPORT.md` :
  - résumé ;
  - tableau des phases ;
  - métriques : cadences reçues, latence par étage, résultats de calibration, VIO contre VO, détection des clés ;
  - captures Rerun ;
  - état du checkpoint (ce qui a été validé sur l'iPhone, ce qui attend des données) ;
  - prochaines étapes vers le guidage et l'audio sur le téléphone.

---

## 4. Critères de réussite (par ordre d'importance)
1. **Acquisition fiable** : l'iPhone 12 envoie au PC au moins 15 images/s et 50 Hz d'IMU pendant 5 min, sans accumulation de retard (âge des images p95 < 200 ms en Wi-Fi local).
2. **Sessions rejouables** : une session enregistrée se rejoue de façon déterministe et sert de test.
3. **Pose robuste** : verticale à moins de 2° grâce à la gravité, moins de pertes en rotation rapide qu'avec la VO seule, échelle tenue par la hauteur caméra.
4. **Chemin en direct** : un chemin vers la cible est calculé et visible en direct dans Rerun, mis à jour à au moins 2 Hz, avec une latence mesurée (objectif p95 < 700 ms).
5. **Prompt fixe** : la gourde fonctionne comme avant ; les clés sont mesurées et documentées.
6. **Suivi** : tout est testé, commité (`phase N: …`), documenté (`PROGRESS.md`, `DECISIONS.md`, `docs/`).
