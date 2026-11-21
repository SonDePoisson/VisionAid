# Calibrations par appareil

Fichiers générés par `uv run python -m visionaid.apps.calibrate_phone` (voir `docs/checkpoint_enregistrements.md`) :

- `<phone.device>_camera.yaml` : K, distorsion, taille d'image, erreur de reprojection ;
- `<phone.device>_imu.yaml` : `R_cam_imu`, biais du gyroscope, décalage temporel image ↔ IMU, correction d'unités.

Ils sont chargés automatiquement (`visionaid.calib.device`). Sans fichier, on utilise `intrinsics.hfov_deg` et les valeurs a priori de `body`.
