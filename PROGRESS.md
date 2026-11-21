# Avancement

| Phase | Statut | Tests | Durée | Notes |
|---|---|---|---|---|
| 0 — Socle | ✅ | 6 passés (unit + data) | ~25 min | open3d épinglé à 0.19 (libusb manquant pour 0.20) |
| 1 — Sources & intrinsèques | ✅ | 12 nouveaux (unit + data) | ~15 min | rotation vérifiée contre l'autorotation ffmpeg |
| 2 — Bus temps réel | ✅ | 14 nouveaux (unit) | ~20 min | HWM relevé à 10 000 (1000 messages en rafale saturaient HWM=1000) |
