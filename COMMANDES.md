# VisionAId — commandes principales

Toutes les commandes se lancent depuis le dossier du projet (`~/VisionAid`). `Ctrl+C` arrête la commande en cours.

> **Règles d'usage**
> - Une seule commande « direct » ou « rejeu temps réel » à la fois : elles utilisent les mêmes ports. Arrête l'une avant de lancer l'autre.
> - Au démarrage, compte environ 25 s de chargement des modèles avant que l'image arrive. Une fenêtre Rerun vide au début, c'est normal.
> - Ne ferme pas la fenêtre Rerun pendant un direct ou un rejeu : sinon le calcul continue, mais plus rien ne s'affiche.
> - Hauteur caméra (`--height`) : en mètres (`1.5`) ou en centimètres (`150`), les deux sont compris.

---

## 1. Direct avec l'iPhone

### Direct + visualisation Rerun
```bash
uv run python -m visionaid.apps.run_live --target "où est ma gourde" --height 150 --rerun live
```
Ensuite, sur l'iPhone, dans Safari : `https://MacBook-Pro-de-Sarah.local:8443/`. Casque (Bluetooth) connecté à l'iPhone, téléphone sur le torse, puis **Démarrer**. Le guidage sonore joue dans le casque ; **Tester le son** vérifie gauche, droite et devant. Désactiver « Audio mono » (Réglages → Accessibilité → Audio/Visuel).

Pour les clés : `--target "où sont mes clés"`.

### Direct + visualisation + enregistrement de la session
```bash
uv run python -m visionaid.apps.run_live --target "où est ma gourde" --height 150 --rerun both --record gourde_essai2
```
- `--record <nom>` enregistre la session dans `data/sessions/<date>_<nom>/`, rejouable ensuite (section 2).
- `--rerun both` affiche Rerun et l'enregistre aussi dans `outputs/live_session.rrd`. Ce fichier est écrasé au prochain direct.

### Enregistrement seul, sans calcul
Plus léger : utile pour la calibration ou pour collecter des données.
```bash
uv run python -m visionaid.apps.run_phone --record cles_essai2 --target "où sont mes clés" --height 150
```

### Options utiles du direct
| Option | Effet |
|---|---|
| `--rerun live` | visualisation seule |
| `--rerun both` | visualisation + fichier `outputs/live_session.rrd` |
| `--rerun file` | fichier seul, sans fenêtre |
| `--rerun off` | rien |
| `--duration 60` | arrêt automatique après 60 s |
| `--demo` | démo : une seule bouteille dans la pièce, la gourde est reconnue dès sa détection (pas de photos de référence ni de couleur) |
| `--depth-width 364` | profondeur plus rapide (−35 % de latence), mais guidage moins précis |

### Demande à la voix (« je cherche ma gourde »)
```bash
uv run python -m visionaid.apps.run_live --command stt --height 150 --rerun live
```
Sans `--target`, le mode voix est choisi tout seul. Sur l'iPhone, après **Démarrer**, la page dit « Appuie sur le grand bouton Parler… ». Appuie sur **🎤 Parler** (bip), dis « je cherche ma gourde » ou « où sont mes clés » : l'enregistrement s'arrête seul après la phrase (ou réappuie). Le PC transcrit (Whisper, ~0,6 s) puis :
1. « Je cherche la gourde. Tourne lentement sur toi-même. », puis le son de recherche ;
2. objet trouvé : le son du chemin se tait le temps d'une phrase qui dit où il est et le trajet (« La gourde est au fond de la pièce, en face de toi, à environ 4 mètres, derrière le canapé, sur la table. Le chemin contourne le canapé par la gauche, suis le son. ») ;
3. guidage par le son du chemin seul ;
4. près du meuble qui porte l'objet (ou à moins de 1,6 m) : « Tu arrives vers la table, la gourde sera légèrement sur ta gauche. », le son du chemin continue jusqu'au son d'arrivée.

Autres demandes : « stop » / « arrête » (silence), une nouvelle demande à tout moment (« je cherche mes clés »). Phrase incomprise : « Je n'ai pas compris… Tu peux chercher tes clés ou ta gourde. », la recherche en cours continue. Le champ « ou écrire » de la page envoie la demande au clavier (tests).

| Option | Effet |
|---|---|
| `--command prompt --target "…"` | objet fixé au lancement (comme avant) ; les annonces vocales sont aussi faites |
| `--command stt` | l'utilisateur dit ce qu'il cherche (bouton Parler) |
| `--stt whisper` | (défaut) le téléphone enregistre, le PC transcrit. Premier lancement : téléchargement du modèle (~1 Go) |
| `--stt phone` | reconnaissance vocale de Safari (Siri et Dictée activés) ; repli sur Whisper en cas d'échec |
| `--tts auto` | (défaut) voix dans le casque du téléphone en direct, sur le haut-parleur du Mac en rejeu |
| `--tts mac` / `--tts off` | voix sur le Mac / aucune voix |

Au démarrage en mode voix, la reconnaissance de chaque objet (fiches `config/targets/`) est préparée (~10 s de plus). Les meubles (table, canapé, chaise, lit, étagère…) sont détectés en même temps que l'objet et servent aux phrases ; ils apparaissent en violet dans la vue Monde 3D (`world/meubles`). Les phrases dites s'affichent dans Rerun (`status`, « voix : … ») et dans le journal.

---

## 2. Rejouer une vidéo déjà tournée (session enregistrée)

Sessions disponibles :
```bash
ls data/sessions
```

### Rejeu « comme le direct », avec la vue Monde 3D
```bash
uv run python -m visionaid.apps.run_live --session data/sessions/20261121-140325_gourde_piece --rerun live
```
L'iPhone n'est pas utilisé. La session repart en boucle à la fin. L'objet recherché est repris automatiquement de la session. Les annonces vocales sont dites par le haut-parleur du Mac (`--tts off` pour les couper).

### Rejeu hors ligne → vidéo annotée avec le son de guidage
```bash
uv run python -m visionaid.apps.run_offline --session data/sessions/20261121-140325_gourde_piece
```
Puis :
```bash
open outputs/annotated_audio.mp4
```
À écouter au casque : les annonces vocales y sont mélangées (voix `Thomas` de macOS, `tts.mac_voice`). Le même rejeu produit aussi `outputs/session.rrd` (ancienne vue Rerun) et `outputs/guidance.wav`.

### Rejeu du guidage sonore seul (réglage des sons)
```bash
uv run python -m visionaid.apps.render_sound data/sessions/<session> --video
```
Écrit dans `outputs/son/<session>/` : `guidage.wav` (au casque) et `camera_son.mp4` (image de la caméra + son, son joué écrit en bas). Le premier lancement rejoue la vision et garde les consignes dans `consignes.json` ; les suivants ne refont que le son, en quelques secondes : on change un réglage de la section `audio` de `config/default.yaml` et on réécoute. `--recompute` rejoue la vision (après un changement du guidage ou de la carte ; nécessaire une fois pour avoir les annonces vocales dans une session déjà calculée).

Pour une session enregistrée sur un autre PC : copier son dossier `data/sessions/<date>_<nom>/` (avec `frames.jsonl`, `meta.json`, `imu.jsonl` et les images) dans `data/sessions/`.

### Résumé des sessions
Durée, images/s, IMU, coupures :
```bash
uv run python -m visionaid.apps.session_info --all
```

---

## 3. Ouvrir un enregistrement Rerun (`.rrd`)

```bash
uv run rerun --port 9877 outputs/live_session.rrd
```
`--port 9877` ouvre une fenêtre séparée. Sans cette option, le fichier s'ajoute à la fenêtre déjà ouverte : il est alors dans le panneau de gauche, section *Recordings*.

Autres enregistrements :
- `outputs/session.rrd` : rejeu hors ligne ;
- `outputs/live_session.rrd` : dernier direct ou rejeu temps réel.

**Naviguer dans la vue 3D :** clic gauche + glisser pour tourner, molette pour zoomer, clic droit + glisser pour déplacer, double-clic pour recadrer. Clique sur l'œil d'un élément dans le panneau de gauche pour le masquer (par exemple `world/nuage`).

---

## 3 bis. Vidéos pour une présentation (MP4 lisibles par PowerPoint)

Exporter une session en trois vidéos : caméra annotée, carte vue de dessus et monde 3D.
```bash
uv run python -m visionaid.apps.export_videos data/sessions/20261121-182903_gourde_direct2
```
Les vidéos sont écrites dans `outputs/videos/<session>/` : `camera.mp4`, `carte.mp4` et `monde3d.mp4` (H.264, environ 1 min de calcul). Option `--only monde3d` pour n'en refaire qu'une.

**Capture vidéo de l'écran Rerun** (outil intégré à macOS) :
1. Ouvre l'enregistrement : `uv run rerun --port 9877 outputs/videos/<session>/live_session.rrd`, puis règle la fenêtre (taille, vues, angle 3D).
2. `Cmd+Maj+5`, puis « Enregistrer la partie sélectionnée de l'écran ». Encadre la fenêtre Rerun et clique sur **Enregistrer**.
3. Dans Rerun, touche ▶ en bas, sur la barre de temps.
4. Arrête l'enregistrement avec le bouton ⏹ de la barre des menus (ou `Cmd+Ctrl+Échap`). La vidéo `.mov` arrive sur le Bureau ; PowerPoint la lit directement.

La première fois, macOS demande l'autorisation « Enregistrement de l'écran » : Réglages Système → Confidentialité et sécurité.

---

## 4. Calibration (une fois par téléphone)

Procédure détaillée : `docs/checkpoint_enregistrements.md`.
```bash
uv run python -m visionaid.apps.run_phone --record calib_camera
```
```bash
open src/visionaid/phone/web/board.html
```
```bash
uv run python -m visionaid.apps.run_phone --record calib_imu --height 150
```
```bash
uv run python -m visionaid.apps.calibrate_phone --camera data/sessions/<…>_calib_camera --imu data/sessions/<…>_calib_imu
```
Résultats dans `config/calib/iphone12_*.yaml`, utilisés automatiquement.

### Démo sonore sur les scénarios simulés (sans modèle)
```bash
uv run python -m visionaid.apps.demo_sound
```
Écrit `outputs/demo_sons/{room_0,corridor_1,appearing_0}.mp4` : scénario simulé avec le son de guidage (à écouter au casque).

### Sons de guidage
Sons d'origine dans `assets/sounds/` (`VisionAid_Sounds 1` à `4`), versions préparées (mono, motif unique, volume égalisé, nappe bouclable) dans `assets/sounds/processed/`. Après avoir changé un son d'origine :
```bash
uv run python -m visionaid.audio.prepare
```
Deux couches superposées :
- **chemin** (son 2 ; son 4 tant que l'objet n'est pas trouvé) : note répétée, pan stéréo vers le chemin (tout à gauche = 100 % oreille gauche, 0 % droite ; chemin derrière = tout du côté du demi-tour le plus court). Le tempo accélère sous 2 m de la cible ;
- **obstacles** (son 1) : nappe en boucle, de plus en plus forte entre 1,5 m et 0,4 m, toujours sous le chemin ;
- **arrivée** (son 3) : une fois, puis silence. Repérage perdu : plus de chemin, nappe à volume moyen.

Réglages (tempo, distances, volumes des obstacles, hystérésis derrière…) : section `audio` de `config/default.yaml`.

---

## 5. Sans iPhone : faux téléphone

Il rejoue la vidéo de l'appartement comme si elle venait du téléphone, pour tester tout le direct.
```bash
uv run python -m visionaid.apps.run_live --fake-phone data/video/appart.mp4 --duration 60 --rerun live
```

---

## 6. Diagnostic du chemin (qualité du guidage sur les sessions)

Mesure, pour chaque session de navigation : quand le premier chemin valide apparaît, le temps passé en recherche, le taux de chemins valides, les départs bloqués et les sauts de direction. Aussi : part des chemins passant par une zone jamais vue (`unknown_path_frac`, doit rester à 0) et sauts de la direction du son d'une image à l'autre (`sound_jumps_over_20`, `sound_jumps_over_45`).
```bash
uv run python -m visionaid.apps.diag_path --all --out outputs/diag
```
Comparer deux diagnostics, par exemple avant et après une modification, et produire l'image de comparaison :
```bash
uv run python -m visionaid.apps.diag_path --compare outputs/diag_avant outputs/diag --png outputs/diag/comparaison.png
```
```bash
open outputs/diag/comparaison.png
```

---

## 7. Tests et vérifications

```bash
make test-fast
```
Environ 190 tests rapides, ~2 min.
```bash
uv run pytest -m data -q --timeout=1800
```
Tests sur les données réelles (sessions, calibration, VIO, clés), ~10 min.
```bash
make night
```
Tout (tests, rejeux, direct simulé), journal dans `outputs/night_run.log`.

---

## 8. Dépannage rapide

| Problème | Solution |
|---|---|
| `address already in use` / port 8443 | un direct ou un rejeu tourne déjà : `Ctrl+C` dans son terminal. En dernier recours : `pkill -f visionaid.apps` |
| Fenêtre Rerun vide | attendre ~25 s (chargement des modèles) ; vérifier qu'elle n'a pas été fermée |
| « Connexion non privée » sur l'iPhone | certificat à installer ou confiance totale à activer : `docs/phone_setup.md`, étape 3 |
| L'iPhone n'atteint pas le Mac | même réseau (Wi-Fi ou partage de connexion de l'iPhone qui filme) ; utiliser l'adresse `.local` affichée |
| Plus de détails | `docs/phone_setup.md` (connexion), `REPORT_PHASE2.md` (bilan), `DECISIONS.md` (choix techniques) |
