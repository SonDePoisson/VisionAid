# Conventions géométriques

- **Repère caméra (OpenCV)** : x vers la droite, y vers le bas, z vers l'avant (axe optique).
- **Repère monde** : origine au centre optique de la première pose. Après alignement sur le sol (phase 6), **z vers le haut**, le plan z = 0 est le sol.
  Avant alignement, le repère monde coïncide avec la première caméra.
- **Poses** : matrices 4×4 `T_world_cam` (float64) ; un point caméra `p_c` devient `p_w = T_world_cam @ [p_c, 1]`.
- **Unités** : mètres, secondes, radians (degrés uniquement dans la config, convertis à la lecture).
- **Grille (costmap)** : indices `(i, j)` = (ligne, colonne) ; `x_monde = origin_x + (j + 0.5) * res`, `y_monde = origin_y + (i + 0.5) * res`.
- **Azimut** (guidage, audio) : angle dans le plan horizontal, relatif à la tête, **positif vers la gauche** (sens trigonométrique vu de dessus, z vers le haut), 0 = droit devant. Élévation positive vers le haut.
- **Image** : après rotation selon les métadonnées vidéo et redimensionnement à `video.width`. Les intrinsèques K correspondent à l'image tournée et redimensionnée.
- **Temps** : chaque message porte `t` (s, horloge de la source = timestamp vidéo) et `frame_idx`.

## Phase 2 : téléphone porté sur le torse

- **Repère appareil (W3C DeviceMotion)** : x vers la droite de l'écran, y vers le haut de l'écran, z sortant de l'écran (vers l'utilisateur). `rotationRate` est donné en deg/s par la spécification (`beta` autour de x, `gamma` autour de y, `alpha` autour de z) : la page envoie `[beta, gamma, alpha]` et le serveur convertit en rad/s. `accelerationIncludingGravity` est en m/s² ; au repos, il vaut **+g selon l'axe dirigé vers le haut** (téléphone vertical en portrait : ≈ (0, +9,81, 0)).
  Attention : certains navigateurs ont inversé les signes ou les unités par le passé ; la calibration de la phase 17 vérifie `R_cam_imu` et les unités sur des données réelles.
- **Caméra arrière en portrait** : `R_cam_imu = diag(1, −1, −1)` a priori (x commun, y caméra vers le bas = −y appareil, z caméra vers l'avant = −z appareil). `ω_cam = R_cam_imu · ω_imu`.
- **Repère corps** (= tête, hypothèse du hackathon) : exprimé dans la **convention caméra** (x droite, y bas, z avant) pour rester compatible avec le code de guidage existant. `T_cam_body` (config `body.T_cam_body`) : identité quand le téléphone est vertical sur le torse. `T_world_body = T_world_cam @ T_cam_body`. `guidance.T_cam_head` est conservé et utilisé seulement si `body.T_cam_body` est absent.
- **Temps** :
  - `t_phone` : horloge du téléphone, `(performance.timeOrigin + performance.now()) / 1000`, la même pour les images et les événements capteurs ;
  - `t_recv` : horloge du PC (`time.time()`) à la réception ;
  - `ClockSync.offset` : `t_pc ≈ t_phone + offset`, estimé par ping/pong (demi-RTT minimal sur une fenêtre glissante).
  - Le `t` des messages issus du téléphone est `t_phone` (horloge de la source, comme le timestamp vidéo en phase 1).
- **Hauteur de caméra** : `body.camera_height_m`, déclarée par l'utilisateur (mesurée au sol), sert de référence d'échelle (phase 18).
