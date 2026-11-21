"""Faux téléphone : client Python qui parle exactement le protocole de la page web.

Sert aux tests de bout en bout et à la mise au point sans iPhone. Rejoue une vidéo (ou un motif
synthétique) et une IMU synthétique, avec décalage d'horloge, gigue et pertes configurables.

Exemple :
    uv run python -m visionaid.phone.fake_phone --url https://localhost:8443/ --duration 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import ssl
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import aiohttp
import cv2
import numpy as np

from visionaid.phone.protocol import PROTOCOL_VERSION, pack_frame

ImuFn = Callable[
    [float], tuple[np.ndarray, np.ndarray]
]  # t (s depuis le début) -> (gyro deg/s, accel)


def synthetic_frames(w: int = 480, h: int = 640) -> Iterator[np.ndarray]:
    """Motif texturé qui défile, avec le numéro d'image incrusté."""
    rng = np.random.default_rng(0)
    base = (rng.random((h, w * 2)) * 255).astype(np.uint8)
    base = cv2.GaussianBlur(base, (0, 0), 3)
    i = 0
    while True:
        x = (i * 4) % w
        g = base[:, x : x + w]
        img = cv2.merge([g, np.roll(g, 7, 0), np.roll(g, 13, 1)])
        cv2.putText(img, str(i), (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        yield img
        i += 1


def video_frames(path: str, max_side: int = 640, loop: bool = True) -> Iterator[np.ndarray]:
    """Images d'une vidéo (rotation appliquée), réduites à `max_side` au plus, en boucle."""
    from visionaid.io.sources import VideoFileSource

    while True:
        src = VideoFileSource(path, width=None, apply_rotation=True)
        for f in src:
            img = f.image
            s = max_side / max(img.shape[:2])
            if s < 1:
                img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            yield img
        src.close()
        if not loop:
            return


def still_imu(noise_gyro: float = 0.2, noise_acc: float = 0.05, seed: int = 0) -> ImuFn:
    """Téléphone vertical immobile : gyro ≈ 0, gravité selon +y (repère W3C)."""
    rng = np.random.default_rng(seed)

    def fn(t: float) -> tuple[np.ndarray, np.ndarray]:
        g = rng.normal(0, noise_gyro, 3)
        a = np.array([0.0, 9.81, 0.0]) + rng.normal(0, noise_acc, 3)
        return g, a

    return fn


def video_gyro_imu(
    path: str, max_side: int = 640, cache_dir: str | None = None
) -> tuple[float, ImuFn]:
    """IMU synthétique cohérente avec une vidéo : gyroscope = rotation visuelle entre images.

    Renvoie (fps de la vidéo, imu_fn). L'accéléromètre est **nul** : la verticale réelle de la
    vidéo est inconnue, une gravité inventée fausserait le sol ; la VIO garde alors la verticale
    par le sol (comportement sans gravité) mais profite du gyroscope. Résultat mis en cache.
    """
    import hashlib
    from pathlib import Path

    from visionaid.calib.imu_cam import visual_rates
    from visionaid.io.intrinsics import from_hfov
    from visionaid.io.sources import VideoFileSource

    p = Path(path)
    key = hashlib.sha1(f"{p.resolve()}|{p.stat().st_size}|{max_side}".encode()).hexdigest()[:10]
    cdir = Path(cache_dir) if cache_dir else p.parent
    cpath = cdir / f".fake_imu_{p.stem}_{key}.npz"
    if cpath.exists():
        z = np.load(cpath)
        t_mid, w, fps = z["t"], z["w"], float(z["fps"])
    else:
        src = VideoFileSource(path, width=None, apply_rotation=True)
        fps = src.fps
        imgs, ts = [], []
        for f in src:
            img = f.image
            s = max_side / max(img.shape[:2])
            if s < 1:
                img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            imgs.append(img)
            ts.append(f.t)
        h, wd = imgs[0].shape[:2]
        K = from_hfov(wd, h, 69.0).K
        t0, t1, w = visual_rates(imgs, np.array(ts) - ts[0], K)
        t_mid = 0.5 * (t0 + t1)
        cdir.mkdir(parents=True, exist_ok=True)
        np.savez(cpath, t=t_mid, w=w, fps=fps)
    R_imu_cam = np.diag([1.0, -1.0, -1.0])  # transposée de R_cam_imu a priori (identique)
    duration = float(t_mid[-1]) if len(t_mid) else 1.0

    def fn(t: float) -> tuple[np.ndarray, np.ndarray]:
        tv = t % max(duration, 1e-6)  # la vidéo reboucle
        wc = (
            np.array([np.interp(tv, t_mid, w[:, k]) for k in range(3)])
            if len(t_mid)
            else np.zeros(3)
        )
        return np.degrees(R_imu_cam @ wc), np.zeros(3)

    return fps, fn


@dataclass
class FakePhoneStats:
    """Compteurs côté faux téléphone."""

    sent_frames: int = 0
    skipped_frames: int = 0  # images non envoyées (attente d'acquittement ou perte simulée)
    acks: int = 0
    ack_timeouts: int = 0
    imu_samples: int = 0
    pongs: int = 0
    welcome: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    send_times: dict = field(default_factory=dict)  # seq -> t_phone d'envoi


class FakePhone:
    """Client WebSocket : hello, images JPEG avec contre-pression, IMU par lots, ping/pong."""

    def __init__(
        self,
        url: str,
        ssl_ctx: ssl.SSLContext | None,
        frames: Iterator[np.ndarray] | None = None,
        imu: ImuFn | None = None,
        fps: float = 15.0,
        imu_hz: float = 60.0,
        imu_batch_ms: float = 50.0,
        jpeg_quality: int = 70,
        clock_offset: float = 0.0,
        jitter_s: float = 0.0,
        drop_rate: float = 0.0,
        ack_timeout_s: float = 1.0,
        protocol: int = PROTOCOL_VERSION,
        seed: int = 0,
    ) -> None:
        self.url = url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        if not self.url.endswith("/ws"):
            self.url += "/ws"
        self.ssl_ctx = ssl_ctx
        self.frames = frames if frames is not None else synthetic_frames()
        self.imu = imu or still_imu(seed=seed)
        self.fps = fps
        self.imu_hz = imu_hz
        self.imu_batch_ms = imu_batch_ms
        self.jpeg_quality = jpeg_quality
        self.clock_offset = clock_offset  # horloge téléphone = horloge PC + clock_offset
        self.jitter_s = jitter_s
        self.drop_rate = drop_rate
        self.ack_timeout_s = ack_timeout_s
        self.protocol = protocol
        self.rng = random.Random(seed)
        self.stats = FakePhoneStats()
        self._waiting_ack = False
        self._sent_at = 0.0
        self._rtt: float | None = None
        self._rtt_id: int | None = None
        self._pings: dict[int, float] = {}
        self._t0 = 0.0

    def now(self) -> float:
        """Horloge du faux téléphone (s)."""
        return time.time() + self.clock_offset

    async def run(self, duration_s: float, calib_frames: int = 0) -> FakePhoneStats:
        """Se connecte, envoie pendant `duration_s` secondes, puis se déconnecte (« bye »)."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.url, ssl=self.ssl_ctx, heartbeat=5.0) as ws:
                await self._session(ws, duration_s, calib_frames)
        return self.stats

    async def _session(self, ws, duration_s: float, calib_frames: int) -> None:
        first = next(self.frames)
        h, w = first.shape[:2]
        await ws.send_str(
            json.dumps(
                {
                    "type": "hello",
                    "protocol": self.protocol,
                    "ua": "FakePhone/1.0 (visionaid tests)",
                    "camera": {"w": w, "h": h},
                    "imu": True,
                    "gyro_units": "deg/s",
                    "t_phone": self.now(),
                }
            )
        )
        self._t0 = time.time()
        recv = asyncio.create_task(self._recv_loop(ws))
        tasks = [
            asyncio.create_task(self._imu_loop(ws, duration_s)),
            asyncio.create_task(self._ping_loop(ws, duration_s)),
            asyncio.create_task(self._frame_loop(ws, duration_s, first, calib_frames)),
        ]
        try:
            res = await asyncio.gather(*tasks, return_exceptions=True)
            for r in res:  # connexion fermée par le serveur : fin normale, sinon on remonte
                if isinstance(r, BaseException) and not isinstance(
                    r, (ConnectionResetError, aiohttp.ClientConnectionResetError)
                ):
                    raise r
            await asyncio.sleep(0.05)  # laisse arriver un éventuel message d'erreur
            if not ws.closed:
                await ws.send_str(json.dumps({"type": "bye"}))
                await asyncio.sleep(0.05)
        finally:
            for t in tasks:
                t.cancel()
            recv.cancel()

    async def _recv_loop(self, ws) -> None:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            m = json.loads(msg.data)
            typ = m.get("type")
            if typ == "ack":
                self.stats.acks += 1
                self._waiting_ack = False
            elif typ == "pong":
                t0 = self._pings.pop(m.get("id"), None)
                if t0 is not None:
                    self._rtt = time.perf_counter() - t0
                    self._rtt_id = m.get("id")
                    self.stats.pongs += 1
            elif typ == "welcome":
                self.stats.welcome = m
            elif typ == "error":
                self.stats.errors.append(m.get("message"))

    async def _frame_loop(self, ws, duration_s: float, first, calib_frames: int) -> None:
        period = 1.0 / self.fps
        img = first
        seq = 0
        for _ in range(calib_frames):  # vues de calibration en tête de session
            seq += 1
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            await ws.send_bytes(
                pack_frame(seq, self.now(), img.shape[1], img.shape[0], buf.tobytes(), True)
            )
        next_t = time.perf_counter()
        while time.time() - self._t0 < duration_s and not ws.closed:
            next_t += period
            await asyncio.sleep(max(0.0, next_t - time.perf_counter()))
            img = next(self.frames)  # la caméra tourne : l'image avance même si on n'envoie pas
            if self._waiting_ack:
                if time.perf_counter() - self._sent_at < self.ack_timeout_s:
                    self.stats.skipped_frames += 1
                    continue
                self.stats.ack_timeouts += 1
            if self.drop_rate and self.rng.random() < self.drop_rate:
                self.stats.skipped_frames += 1
                continue
            t_cap = self.now()
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if self.jitter_s:
                await asyncio.sleep(self.rng.uniform(0, self.jitter_s))
            seq += 1
            self._waiting_ack = True
            self._sent_at = time.perf_counter()
            self.stats.send_times[seq] = t_cap
            await ws.send_bytes(pack_frame(seq, t_cap, img.shape[1], img.shape[0], buf.tobytes()))
            self.stats.sent_frames += 1

    async def _imu_loop(self, ws, duration_s: float) -> None:
        buf: list[list[float]] = []
        period = 1.0 / self.imu_hz
        next_t = time.perf_counter()
        last_flush = time.perf_counter()
        while time.time() - self._t0 < duration_s and not ws.closed:
            next_t += period
            await asyncio.sleep(max(0.0, next_t - time.perf_counter()))
            t = time.time() - self._t0
            g, a = self.imu(t)
            buf.append([self.now(), *map(float, g), *map(float, a)])
            if (time.perf_counter() - last_flush) * 1000 >= self.imu_batch_ms:
                await ws.send_str(json.dumps({"type": "imu", "samples": buf}))
                self.stats.imu_samples += len(buf)
                buf = []
                last_flush = time.perf_counter()
        if buf and not ws.closed:
            await ws.send_str(json.dumps({"type": "imu", "samples": buf}))
            self.stats.imu_samples += len(buf)

    async def _ping_loop(self, ws, duration_s: float) -> None:
        pid = 0
        while time.time() - self._t0 < duration_s and not ws.closed:
            pid += 1
            self._pings[pid] = time.perf_counter()
            await ws.send_str(
                json.dumps(
                    {
                        "type": "ping",
                        "id": pid,
                        "t_phone": self.now(),
                        "prev_id": self._rtt_id,
                        "rtt": self._rtt,
                    }
                )
            )
            await asyncio.sleep(0.25 if pid < 5 else 1.0)  # quelques pings rapprochés au début


def run_fake_phone(phone: FakePhone, duration_s: float, calib_frames: int = 0) -> FakePhoneStats:
    """Version synchrone de `FakePhone.run`."""
    return asyncio.run(phone.run(duration_s, calib_frames))


def main(argv=None) -> None:
    from visionaid.phone.certs import client_ssl_context, ensure_certs
    from visionaid.utils.config import load_config, resolve_path

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default=None)
    ap.add_argument("--video", default=None, help="vidéo à rejouer (sinon motif synthétique)")
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--clock-offset", type=float, default=0.0)
    ap.add_argument("--jitter", type=float, default=0.0)
    args = ap.parse_args(argv)
    cfg = load_config()
    url = args.url or f"https://localhost:{cfg.phone.https_port}/"
    ssl_ctx = client_ssl_context(ensure_certs(resolve_path(cfg.phone.certs_dir)))
    frames = video_frames(args.video) if args.video else synthetic_frames()
    phone = FakePhone(
        url, ssl_ctx, frames, fps=args.fps, clock_offset=args.clock_offset, jitter_s=args.jitter
    )
    st = run_fake_phone(phone, args.duration)
    print(
        json.dumps(
            {k: v for k, v in st.__dict__.items() if k != "send_times"}, indent=2, default=str
        )
    )


if __name__ == "__main__":
    main()
