# Checkpoint : enregistrements avec l'iPhone 12

Ces enregistrements sont les seules données que je ne peux pas produire moi-même. Elles servent à calibrer la caméra et les capteurs, à mesurer la pose fusionnée et à tester la détection des clés. Le reste du plan avance sans elles : les tests qui en dépendent sont `skip` tant qu'elles manquent.

Durée totale : environ 30 minutes.

## Avant de commencer
- Suivre `docs/phone_setup.md` : réseau, certificat installé, page qui s'ouvre sans avertissement.
- Mesurer au mètre la **hauteur de la caméra** du téléphone fixé sur le torse, depuis le sol (par exemple 1,32 m).
- Fixer le téléphone **en portrait, écran vers soi, caméra arrière vers l'avant**. La bulle du niveau doit être verte.
- Photographier les clés : **5 à 10 photos** sur des fonds variés, à copier dans `data/ref/cles_1.jpg`, `cles_2.jpg`, etc. L'appareil photo normal suffit.

Chaque enregistrement se lance par une commande sur le PC. Ensuite, on touche **Démarrer** sur le téléphone, puis **Arrêter** à la fin. `Ctrl+C` arrête le serveur.

## 1. Calibration de la caméra (`calib_camera`)
```bash
uv run python -m visionaid.apps.run_phone --record calib_camera
```
1. Sur le PC, ouvrir `https://localhost:8443/calib/board` en plein écran, luminosité au maximum. Mesurer à la règle le **côté d'une case** (en mm) et le noter.
2. Sur le téléphone, cocher **Mode calibration**. Le téléphone est tenu en main, pas sur le torse.
3. Prendre **15 à 20 vues** avec « Capturer une vue » :
   - de face, de biais (gauche, droite, haut, bas, environ 30-45°) ;
   - de près et de loin ;
   - le damier visible en entier et net sur chaque vue.
4. Dans le champ Notes, écrire `case = <mm> mm`, puis « Envoyer les notes ».

## 2. Calibration des capteurs (`calib_imu`)
```bash
uv run python -m visionaid.apps.run_phone --record calib_imu --height <hauteur>
```
Téléphone sur le torse, face à une zone texturée (étagère, mur avec des objets), en mode normal :
1. **5 s immobile**.
2. **3 rotations lentes** sur place, environ 90° à gauche puis retour, puis 90° à droite et retour.
3. **3 rotations rapides**, mêmes amplitudes.
4. Pencher le buste en avant puis en arrière, 2 fois.
5. **5 s immobile**.

## 3. Sessions de navigation
Pour chacune, lancer la commande, se placer au départ, toucher Démarrer, faire le parcours, puis Arrêter.

| Nom | Commande | Parcours |
|---|---|---|
| `gourde_piece` | `--record gourde_piece --target "où est ma gourde" --height <h>` | Partir à 3-4 m de la gourde posée sur un meuble, sans la regarder. Tourner lentement sur place jusqu'à la voir, puis marcher jusqu'à elle en évitant les meubles. |
| `cles_piece` | `--record cles_piece --target "où sont mes clés" --height <h>` | Idem, avec les clés posées sur un meuble (table, commode). |
| `couloir` | `--record couloir --target "où est ma gourde" --height <h>` | Traverser un couloir ou un passage avec 1 ou 2 obstacles (chaise, sac), la gourde au bout. |
| `rotations_rapides` | `--record rotations_rapides --height <h>` | Sur place : tourner vite à gauche et à droite, environ 180° à chaque fois, pendant 30 s, puis marcher 3 m. |

La commande complète est `uv run python -m visionaid.apps.run_phone …`.

## 4. Vérifier
```bash
uv run python -m visionaid.apps.session_info --all
```
Pour chaque session, vérifier :
- `fps_median` ≥ 15 ;
- `imu_hz` ≥ 50 ;
- `gaps_over_3_periods` proche de 0 ;
- `frame_age_ms_p95` < 200 ms.

## Checklist de la page web
- [ ] HTTPS accepté sans avertissement après l'installation du certificat.
- [ ] Permissions des capteurs et de la caméra obtenues en un seul geste.
- [ ] L'écran ne se met pas en veille pendant 5 minutes.
- [ ] Au moins 15 images/s reçues et au moins 50 Hz d'IMU pendant 5 minutes, sans dérive de l'âge des images.
- [ ] Reconnexion automatique après une coupure du Wi-Fi : couper le Wi-Fi du téléphone 5 s, puis le remettre.

Noter les problèmes rencontrés (chauffe, coupures, gêne du support) dans le champ Notes de la page, ou me les dire directement.

## Ensuite
Me dire que les données sont dans `data/sessions/` et `data/ref/`. Je lance alors :
- la calibration de la caméra et des capteurs (phase 17) ;
- les tests `data` des phases 16 à 20 ;
- le rejeu des sessions dans le pipeline complet.
