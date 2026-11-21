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
Ensuite, sur l'iPhone, dans Safari : `https://MacBook-Pro-de-Sarah.local:8443/`. Téléphone sur le torse, puis **Démarrer**.

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
| `--depth-width 364` | profondeur plus rapide (−35 % de latence), mais guidage moins précis |

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
L'iPhone n'est pas utilisé. La session repart en boucle à la fin. L'objet recherché est repris automatiquement de la session.

### Rejeu hors ligne → vidéo annotée avec le son de guidage
```bash
uv run python -m visionaid.apps.run_offline --session data/sessions/20261121-140325_gourde_piece
```
Puis :
```bash
open outputs/annotated_audio.mp4
```
À écouter au casque. Le même rejeu produit aussi `outputs/session.rrd` (ancienne vue Rerun) et `outputs/guidance.wav`.

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

---

## 5. Sans iPhone : faux téléphone

Il rejoue la vidéo de l'appartement comme si elle venait du téléphone, pour tester tout le direct.
```bash
uv run python -m visionaid.apps.run_live --fake-phone data/video/appart.mp4 --duration 60 --rerun live
```

---

## 6. Tests et vérifications

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

## 7. Dépannage rapide

| Problème | Solution |
|---|---|
| `address already in use` / port 8443 | un direct ou un rejeu tourne déjà : `Ctrl+C` dans son terminal. En dernier recours : `pkill -f visionaid.apps` |
| Fenêtre Rerun vide | attendre ~25 s (chargement des modèles) ; vérifier qu'elle n'a pas été fermée |
| « Connexion non privée » sur l'iPhone | certificat à installer ou confiance totale à activer : `docs/phone_setup.md`, étape 3 |
| L'iPhone n'atteint pas le Mac | même réseau (Wi-Fi ou partage de connexion de l'iPhone qui filme) ; utiliser l'adresse `.local` affichée |
| Plus de détails | `docs/phone_setup.md` (connexion), `REPORT_PHASE2.md` (bilan), `DECISIONS.md` (choix techniques) |
