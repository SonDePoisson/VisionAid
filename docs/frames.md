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
