"""Nom Bonjour « visionaid.local » : le téléphone ouvre https://visionaid.local:PORT/
au lieu d'une adresse IP en quatre nombres.

On annonce en mDNS un service HTTPS dont l'hôte est « visionaid.local » : cela publie
les enregistrements A/AAAA de ce nom vers les adresses du Mac. Les adresses suivent
les changements de réseau (`update`). Sans la bibliothèque zeroconf ou sans réseau,
rien n'est annoncé et les adresses IP restent proposées.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading

log = logging.getLogger(__name__)

BONJOUR_HOST = "visionaid.local"
_SERVICE_TYPE = "_https._tcp.local."

_lock = threading.Lock()
_active: Announcer | None = None


def available() -> bool:
    """Vrai si le nom peut être annoncé (bibliothèque zeroconf présente)."""
    try:
        import zeroconf  # noqa: F401
    except ImportError:
        return False
    return True


def announced() -> bool:
    """Vrai si « visionaid.local » est annoncé par ce processus."""
    return _active is not None


class Announcer:
    def __init__(self, port: int) -> None:
        self.port = int(port)
        self._zc = None
        self._info = None
        self._ips: list[str] = []

    @staticmethod
    def _addresses(ips: list[str]) -> list[bytes]:
        out = []
        for a in ips:
            ip = ipaddress.ip_address(a)
            out.append(socket.inet_pton(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, a))
        return out

    def _make_info(self, ips: list[str]):
        from zeroconf import ServiceInfo

        return ServiceInfo(
            _SERVICE_TYPE,
            f"VisionAid.{_SERVICE_TYPE}",
            addresses=self._addresses(ips),
            port=self.port,
            properties={"path": "/"},
            server=f"{BONJOUR_HOST}.",
        )

    def start(self, ips: list[str]) -> bool:
        global _active
        if not ips:
            return False
        try:
            from zeroconf import IPVersion, Zeroconf
        except ImportError:
            log.info("zeroconf absent : pas de nom %s, seulement les adresses IP.", BONJOUR_HOST)
            return False
        try:
            self._zc = Zeroconf(ip_version=IPVersion.All)
            self._info = self._make_info(ips)
            self._zc.register_service(self._info, allow_name_change=True)
        except Exception as e:  # réseau sans multicast, nom pris…
            log.warning("Annonce de %s impossible : %s", BONJOUR_HOST, e)
            self.stop()
            return False
        self._ips = list(ips)
        with _lock:
            _active = self
        log.info("Téléphone : https://%s:%d/ annoncé (Bonjour)", BONJOUR_HOST, self.port)
        return True

    def update(self, ips: list[str]) -> None:
        """Nouvelles adresses après un changement de réseau."""
        if self._zc is None or not ips or sorted(ips) == sorted(self._ips):
            return
        try:
            info = self._make_info(ips)
            info.name = self._info.name  # garde le nom éventuellement renommé
            self._zc.update_service(info)
            self._info, self._ips = info, list(ips)
        except Exception as e:
            log.warning("Mise à jour de %s impossible : %s", BONJOUR_HOST, e)

    def stop(self) -> None:
        global _active
        with _lock:
            if _active is self:
                _active = None
        zc, self._zc = self._zc, None
        if zc is None:
            return
        try:
            if self._info is not None:
                zc.unregister_service(self._info)
        except Exception:
            pass
        try:
            zc.close()
        except Exception:
            pass
