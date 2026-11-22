# Protocole téléphone → PC (version 1)

La page `https://<pc>:8443/` ouverte dans le navigateur du téléphone envoie la caméra et les capteurs au serveur (`apps/run_phone.py`) sur un WebSocket sécurisé `wss://<pc>:8443/ws`. Le certificat est émis par une autorité locale générée sur le PC. Son certificat racine est téléchargeable en HTTP simple sur `http://<pc>:8080/ca.crt` (voir `docs/phone_setup.md`).

Un seul téléphone est connecté à la fois. Une nouvelle connexion remplace l'ancienne.

## Téléphone → PC

### Messages texte (JSON)

| `type` | Champs | Rôle |
|---|---|---|
| `hello` | `protocol` (int), `ua` (user agent), `camera: {w, h}`, `imu` (bool), `gyro_units` (`"deg/s"`), `t_phone` | Premier message obligatoire. Version inconnue : `error` puis fermeture. |
| `imu` | `samples: [[t, gx, gy, gz, ax, ay, az], …]` | Lot toutes les ~50 ms. `t` en s (horloge du téléphone), gyro dans l'unité annoncée, accélération gravité incluse en m/s², repère appareil W3C. |
| `ping` | `id`, `t_phone`, `prev_id`, `rtt` | Toutes les secondes. `rtt` (s) est l'aller-retour mesuré pour le ping `prev_id` (l'échange précédent) : le PC apparie ainsi délai et RTT du même échange. |
| `notes` | `text` | Notes libres, enregistrées dans `meta.json` de la session. |
| `command` | `text`, `alternatives` (liste, facultatif), `source` | Demande de l'utilisateur déjà en texte (reconnaissance de Safari, ou saisie) : « je cherche ma gourde », « stop ». Mode `stt` seulement. |
| `command_audio` | `mime` (`audio/mp4`…), `data` (base64) | Demande enregistrée (quelques secondes), transcrite par Whisper sur le PC. |
| `bye` | — | Arrêt volontaire. |

### Messages binaires (images)
Structure : `[4 octets : longueur L de l'en-tête, big-endian][L octets : en-tête JSON UTF-8][JPEG]`.

En-tête : `{"type": "frame", "seq": int, "t_phone": float, "w": int, "h": int, "calib": bool}`.
- `seq` est strictement croissant.
- `calib = true` marque une image de calibration, envoyée à pleine résolution et à la demande. Le serveur l'enregistre, mais ne la publie pas sur le bus de traitement.

**Contre-pression** : le PC acquitte une image **après l'avoir décodée et transmise** au traitement. Le téléphone n'envoie l'image `seq` qu'après avoir reçu `ack` pour l'image précédente, ou après `ack_timeout_s` (1 s) en cas de perte. Il saisit toujours l'image la plus récente au moment de l'envoi : rien ne s'accumule.

## PC → téléphone (JSON)

| `type` | Champs | Rôle |
|---|---|---|
| `welcome` | `protocol`, `session` (nom ou `null`), `max_fps`, `jpeg_quality`, `imu_batch_ms`, `capture_width`, `capture_height`, `ack_timeout_s`, `ping_interval_s`, `audio` | Réponse à `hello`, avec les réglages imposés par le PC. `audio` : réglages du rendu sonore (voir plus bas), ou `null` si les sons sont absents. |
| `ack` | `seq` | Image reçue et décodée. |
| `pong` | `id`, `t_phone`, `t_pc` | Réponse au ping. |
| `stats` | `fps_in`, `imu_hz`, `offset_ms`, `rtt_ms`, `frame_age_ms` | Toutes les secondes, pour l'affichage sur le téléphone. |
| `error` | `message` | Erreur fatale (version, format), suivie de la fermeture. |
| `sound` | `t`, `state`, `mode`, `az`, `pan`, `dist`, `interval`, `gain_db`, `obstacle_db`, `event` | Consigne sonore, ~20 par seconde (`realtime.cue_hz`). Voir « Son ». |
| `speech` | `id`, `text`, `duck` | Phrase à dire (synthèse vocale du navigateur), une fois par `id`. `duck` : la couche chemin se tait jusqu'à la fin de la phrase (annonce de l'objet trouvé) ; les obstacles restent audibles. |
| `heard` | `text`, `action` (`search`, `stop`, `unknown`), `target` | Ce que le PC a compris de la demande (affichage). |

`welcome.voice` : `mode` (`prompt` ou `stt`), `stt` (`whisper` ou `phone`), `max_record_s`, `tts` (le téléphone dit les phrases), `lang`, `rate`, `target` (nom de l'objet en mode `prompt`). En mode `stt`, la page affiche le grand bouton **Parler** ; le micro n'est ouvert que pendant la demande (un casque Bluetooth repasse ensuite en stéréo).

## Son (PC → téléphone → casque)

Le PC décide quoi jouer (`audio/director.py`), le téléphone l'exécute avec Web Audio (`web/audio.js`). Les sons sont servis par le PC sur `/sounds/<fichier>` (dossier `audio.sounds_dir`). Deux couches superposées : le **chemin** (note répétée, pan stéréo) et les **obstacles** (nappe en boucle, volume selon la distance).

`welcome.audio` : `sounds` (`guide`, `search`, `arrived`, `obstacle` → URL), `gains_db` (par son), `master_gain_db`, `smoothing_s` (pan), `obstacle_smoothing_s`, `lost_obstacle_db`, `watchdog_s`.

Message `sound` :

| Champ | Sens |
|---|---|
| `mode` | couche chemin : `search` (son de recherche répété), `guide` (note du chemin répétée), `lost` (repérage perdu : plus de chemin), `arrived` (silence après le son d'arrivée), `silent` |
| `az` | direction du chemin (rad, positif à gauche) |
| `pan` | pan stéréo à puissance constante : −1 = tout à gauche (rien à droite), 0 = centre, +1 = tout à droite. Chemin derrière : ±1 du côté du demi-tour le plus court |
| `interval` | espacement entre deux notes (s), réduit sous `audio.guide_accel_m` de la cible |
| `gain_db` | gain de la note |
| `obstacle_db` | gain de la nappe des obstacles (≤ −120 : muette), lissé sur `obstacle_smoothing_s` |
| `event` | `arrived` : jouer le son d'arrivée une fois |

Sans message `sound` depuis `watchdog_s` (1,5 s) pendant le guidage, le téléphone passe en « repérage perdu » (plus de chemin, nappe à `lost_obstacle_db`) : un guide figé serait dangereux.

## Publication sur le bus (côté PC)
- `frame` → `Frame(t=t_phone, frame_idx=seq, image=BGR redimensionnée à video.width, K, t_phone, t_recv)`.
- `imu` → `ImuBatch` (gyro converti en rad/s), un message par lot reçu.
- `clock` → `ClockSync` à chaque mise à jour du décalage.

## Session enregistrée
Dossier `data/sessions/<AAAAMMJJ-HHMMSS>_<nom>/` (ignoré par git) :

| Fichier | Contenu |
|---|---|
| `frames/<seq:06d>.jpg` | JPEG reçus, sans recompression |
| `calib/<seq:06d>.jpg` | images de calibration (`calib = true`) |
| `frames.jsonl` | `{"seq", "t_phone", "t_recv", "w", "h", "file"}` par image |
| `imu.jsonl` | `{"t", "gyro": [rad/s ×3], "accel": [m/s² ×3], "t_recv"}` par échantillon |
| `clock.jsonl` | `{"t_recv", "offset", "uncertainty", "rtt"}` |
| `meta.json` | `protocol`, `ua`, `camera`, `gyro_units`, `camera_height_m`, `target`, `notes`, début/fin, nombre d'images et d'échantillons |
| `video.mp4` | facultatif, généré par `apps/session_info.py` pour la visualisation |
