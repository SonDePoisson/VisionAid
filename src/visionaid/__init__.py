"""VisionAId : guidage sonore binaural vers un objet, pour personnes malvoyantes."""

import os

# Un token HF expiré présent sur la machine fait échouer les téléchargements de modèles
# publics : on n'envoie pas de token implicite (les modèles utilisés sont publics).
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import warnings as _warnings

# numpy 2.x + Accelerate (macOS arm64) émet des RuntimeWarning parasites sur les matmul.
_warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)
