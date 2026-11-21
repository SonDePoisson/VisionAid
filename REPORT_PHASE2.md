# VisionAId — Rapport phase 2 : du téléphone au chemin (21 novembre 2026)

Plan exécuté : `PLAN_PHASE2.md`, phases 14 à 22. Le détail est dans `PROGRESS.md`, les choix dans `DECISIONS.md`.

## Résumé

1. **Acquisition depuis le téléphone, prête à tester sur l'iPhone 12.** Le PC sert une page web en HTTPS, avec un certificat d'une autorité locale à installer une fois. La page envoie au PC, par WebSocket, la caméra arrière en JPEG et le gyroscope et l'accéléromètre horodatés sur la même horloge. Elle n'a **pas encore tourné sur un vrai téléphone** : c'est le checkpoint.
2. **Contre-pression sans accumulation de retard.** Le PC acquitte chaque image après l'avoir prise en charge, et le téléphone n'envoie la suivante qu'à ce moment-là. Avec un PC 2,5 fois trop lent, l'âge des images reste sous 2 périodes (test).
3. **Horloge synchronisée** par ping/pong apparié : décalage retrouvé à ±20 ms près en test.
4. **Sessions enregistrées et rejouables** à l'identique : en offline, en temps réel et dans les tests, comme une vidéo.
5. **Calibration automatique**, validée sur données synthétiques :
   - caméra au damier, affiché sur l'écran du PC : K retrouvée à moins de 2 % ;
   - gyroscope ↔ caméra : biais à moins de 10 %, décalage temporel à moins de 5 ms, orientation à moins de 2° ;
   - une erreur d'unités deg/s ↔ rad/s est détectée et corrigée.
6. **Pose fusionnée (VIO).**
   - Le gyroscope prédit la rotation, l'accéléromètre fixe la verticale (erreur sous 2° avec une marche simulée).
   - Si la vidéo décroche, l'orientation continue au gyroscope pendant 2 s (état `degraded`). En rotation rapide avec flou simulé : **0 % de pertes**, contre 55 % pour la VO seule.
   - L'échelle de la profondeur se recale sur la hauteur de caméra déclarée.
7. **Prompt fixe.** « Où est ma gourde » ou « où sont mes clés » choisit une fiche cible : prompts de détection, photos de référence, modèle de couleur, seuil. Sans photo, les clés sont reconnues par le texte seul. La gourde est inchangée : 8 tests lents de non-régression verts.
8. **Graphe temps réel du téléphone au chemin.** Avec le faux téléphone rejouant la vidéo et les vrais modèles :
   - chemins valides à **4,1 Hz** ;
   - latence capture → chemin **p50 336 ms, p95 415 ms**, objectif 700 ms ;
   - chemin invalidé pendant une coupure, puis reprise automatique.
9. **Optimisation testée et écartée.** Une profondeur à 364 px réduit la latence p95 à 275 ms, mais dégrade nettement le guidage (7° → 46°). On garde 518 px.
10. **Tests** : 176 rapides et 30 lents (ou `data`). Les tests sur données réelles du téléphone sont `skip` tant que les enregistrements manquent. Aucun test supprimé, aucun seuil affaibli.

## Ce qui attend l'équipe (checkpoint)

Tout est décrit pas à pas dans [`docs/checkpoint_enregistrements.md`](docs/checkpoint_enregistrements.md), avec la mise en route dans [`docs/phone_setup.md`](docs/phone_setup.md). Environ 30 minutes :

1. installer le certificat sur l'iPhone et valider la checklist de la page web ;
2. enregistrer les sessions `calib_camera` (damier), `calib_imu` (rotations), `gourde_piece`, `cles_piece`, `couloir`, `rotations_rapides`, avec la hauteur de caméra mesurée ;
3. copier 5 à 10 photos des clés dans `data/ref/cles_*.jpg`.

Ensuite, ces commandes déroulent tout le reste :
```bash
uv run python -m visionaid.apps.calibrate_phone --camera data/sessions/<…>_calib_camera --imu data/sessions/<…>_calib_imu
uv run pytest -m "data" -q --timeout=1800
make night
```
Pour le direct :
```bash
uv run python -m visionaid.apps.run_live --target "où est ma gourde" --height 1.32
```
Cette commande ouvre Rerun, qui affiche en direct l'image annotée, la carte, la trajectoire, le chemin et la cible.

## Tableau des phases

| Phase | Statut | Tests | Remarque |
|---|---|---|---|
| 14 Socle | ✅ | 6 | messages IMU/horloge, protocole documenté |
| 15 Serveur et page web | ✅, page à valider sur iPhone | 8 + 5 | HTTPS avec autorité locale, WebSocket, faux téléphone |
| 16 Rejeu de sessions | ✅ | 7 + 2 + 1 data | vidéo ou session partout (offline, temps réel, caches) |
| ⏸ Checkpoint | en attente | — | procédure écrite |
| 17 Calibration | ✅ synthétique, ⏸ réel | 9 + 2 data | damier, gyroscope ↔ caméra, unités |
| 18 VIO | ✅ synthétique, ⏸ réel | 10 + 2 data | gyroscope, gravité, `degraded`, échelle |
| 19 Prompt fixe | ✅ gourde, ⏸ clés | 19 + 1 + 1 data | fiches cibles, ReID générique |
| 20 Temps réel jusqu'au chemin | ✅ faux téléphone, ⏸ iPhone | 1 + 2 lents | 4,1 Hz, p95 415 ms |
| 21 Optimisations | ⚠️ partiel | — | 364 px mesuré, non retenu |
| 22 Rapport | ✅ | — | `night_run.sh` étendu |

## Métriques clés

| Domaine | Mesure | Valeur | Source |
|---|---|---|---|
| Transport | âge des images p95 (local, 15 img/s) | < 133 ms (2 périodes) | test faux téléphone |
| Transport | consommateur 2,5 fois trop lent | images toujours fraîches, aucune file | test |
| Horloge | décalage retrouvé | ± 20 ms (synthétique : ± demi-RTT) | test |
| Calibration caméra | K, damier synthétique | < 2 %, reprojection < 0,5 px | test |
| Calibration IMU | décalage / biais / rotation | < 5 ms / < 10 % / < 2° | test |
| VIO | verticale (marche simulée) | < 2° | test |
| VIO | rotation rapide avec flou | 0 % `lost` (VO seule : 55 %) | test |
| VIO | coupure vidéo 1 s | orientation < 3°, retour à `ok` en < 4 images | test |
| Échelle | profondeur biaisée de 30 % | corrigée à < 5 % | test |
| Temps réel, stubs | premier chemin valide | 5,6 s après la connexion | test |
| Temps réel, vidéo + vrais modèles | chemins valides | 4,1 Hz | faux téléphone, 30 s |
| Temps réel, vidéo + vrais modèles | capture → chemin p50 / p95 | 336 / 415 ms (objectif 700) | faux téléphone, 30 s |
| Temps réel, vidéo + vrais modèles | géométrie (profondeur + VIO) | ~165 ms par image, 5,4 Hz | faux téléphone, 30 s |
| Profondeur 364 px | capture → chemin p95 | 275 ms, mais guidage 46° (contre 7°) | non retenu |
| Offline (non-régression) | état final / distance | ARRIVED à 0,18 m | vidéo d'origine |

## Décisions importantes (détail dans `DECISIONS.md`)

- **WebSocket + JPEG plutôt que WebRTC** : horodatage exact sur l'horloge des capteurs, pas de négociation réseau fragile, contre-pression simple. WebRTC n'apporterait rien de mesurable en réseau local.
- **Acquittement après ingestion** : le téléphone ne va jamais plus vite que le PC.
- **VIO par composition, sans filtre de Kalman.** La position reste visuelle : la double intégration de l'accéléromètre d'un téléphone dérive en moins d'une seconde. Le gyroscope sert de prédiction, de contrôle et de repli. L'accéléromètre sert de verticale.
- **Sol contraint par la gravité** quand elle est connue, et **échelle par la hauteur de caméra** : remplace le facteur fixe 0,76 calibré sur une seule vidéo.
- **Fiches cibles = surcharges de config.** Sans `--target`, rien ne change : c'est la gourde, comme avant.
- **Planificateur avec chien de garde** : jamais de chemin périmé après une coupure.

## Limites connues

- **Rien n'a encore tourné sur un vrai téléphone.** Plusieurs points ne seront vérifiés qu'au checkpoint :
  - les permissions Safari et la tenue de l'écran allumé ;
  - les signes et unités réels du gyroscope (la calibration les vérifie) ;
  - la cadence réelle de l'IMU et la latence Wi-Fi.
- **La gravité et l'échelle n'ont été validées qu'en synthétique.** Le test sur la vraie vidéo n'a pas de vraie gravité : l'accéléromètre y est nul faute de données.
- **Clés** : aucun chiffre réel. En texte seul, deux objets de la même catégorie ne sont pas distingués.
- **Pose `degraded`** : la position est gelée. Si l'utilisateur marche pendant une perte visuelle de plus d'une seconde, la position dérive jusqu'à la relocalisation.
- **Android** : code compatible (permissions, certificat), mais non testé faute d'appareil.
- **Distorsion de la caméra** : estimée mais non corrigée dans le pipeline (sténopé).

## Prochaines étapes

1. **Checkpoint** : enregistrements avec l'iPhone, calibration, tests `data`. C'est le préalable à tout le reste.
2. **Guidage** (étape suivante du projet) : le PC publie déjà la cible et le chemin en coordonnées monde. Il reste à les renvoyer au téléphone (canal retour sur le même WebSocket) et à rendre le son sur le téléphone avec sa propre orientation, avec la Web Audio API et son `PannerNode` HRTF : c'est la boucle rapide. La page web est le bon point de départ.
3. Si la pose réelle est trop instable : passer par ARKit dans une petite application native. Sans LiDAR, la pose ARKit reste meilleure que notre VIO.
4. Options du schéma : mémoire, visage, support.

## Comment reprendre

```bash
make test-fast                       # 176 tests rapides, ~2 min
make run-phone                       # acquisition seule (enregistrer : --record <nom>)
make run-live                        # téléphone → chemin, Rerun en direct
make run-live-fake                   # idem avec le faux téléphone (vidéo de l'appartement)
uv run python -m visionaid.apps.session_info --all
make night                           # tout, journalisé dans outputs/night_run.log
```
