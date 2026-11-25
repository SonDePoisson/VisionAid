"""Icônes de l'application (icon.png, icon.ico, icon.icns) dessinées d'après le logo de l'interface.

Le logo (`#logo` dans src/visionaid/app/web/index.html) : un point encre et deux ondes, la
seconde dorée, sur fond crème. Dessiné en grand puis réduit pour des bords lisses.

    uv run python packaging/make_icons.py   # écrit dans packaging/build/icons/
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

CREAM = (251, 246, 236, 255)
INK = (22, 35, 59, 255)
GOLD = (201, 122, 18, 255)
SIZE = 1024
SS = 4  # sur-échantillonnage


def draw_logo(size: int = SIZE) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # carré arrondi façon icône macOS (marge ~10 %)
    m = int(s * 0.10)
    d.rounded_rectangle((m, m, s - m, s - m), radius=int(s * 0.18), fill=CREAM)
    # logo 40×40 → zone centrale de 60 % du carré
    inner = s - 2 * m
    k = inner * 0.80 / 40.0
    ox = m + (inner - 40 * k) / 2 + 1 * k  # dessin (x 7→29) recentré
    oy = m + (inner - 40 * k) / 2

    def P(x: float, y: float) -> tuple[float, float]:
        return ox + x * k, oy + y * k

    r = 5 * k
    cx, cy = P(12, 20)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    w = int(3 * k)
    # arcs SVG « M21 11 a13 13 0 0 1 0 18 » et « M27 6 a20 20 0 0 1 0 28 » : centre de courbure
    # sur y=20, à distance √(r² − (corde/2)²) à gauche de la corde
    for x0, half, rad, col in ((21, 9, 13, INK), (27, 14, 20, GOLD)):
        dist = math.sqrt(rad * rad - half * half)
        ccx, ccy = P(x0 - dist, 20)
        R = rad * k
        ang = math.degrees(math.atan2(half, dist))
        d.arc(
            (ccx - R - w / 2, ccy - R - w / 2, ccx + R + w / 2, ccy + R + w / 2),
            start=-ang,
            end=ang,
            fill=col,
            width=w,
        )
        for a in (-ang, ang):  # bouts arrondis
            ex = ccx + R * math.cos(math.radians(a))
            ey = ccy + R * math.sin(math.radians(a))
            d.ellipse((ex - w / 2, ey - w / 2, ex + w / 2, ey + w / 2), fill=col)
    return img.resize((size, size), Image.LANCZOS)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    img = draw_logo()
    img.save(out / "icon.png")
    img.resize((512, 512), Image.LANCZOS).save(out / "icon-512.png")
    img.save(out / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(out / "icon.icns")
    print(f"icônes écrites dans {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "build" / "icons")
