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
| `welcome` | `protocol`, `session` (nom ou `null`), `max_fps`, `jpeg_quality`, `imu_batch_ms`, `capture_width`, `capture_height`, `ack_timeout_s`, `ping_interval_s` | Réponse à `hello`, avec les réglages imposés par le PC. |
| `ack` | `seq` | Image reçue et décodée. |
| `pong` | `id`, `t_phone`, `t_pc` | Réponse au ping. |
| `stats` | `fps_in`, `imu_hz`, `offset_ms`, `rtt_ms`, `frame_age_ms` | Toutes les secondes, pour l'affichage sur le téléphone. |
| `error` | `message` | Erreur fatale (version, format), suivie de la fermeture. |

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
