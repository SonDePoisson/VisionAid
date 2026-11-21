"""Autorité de certification locale et certificat serveur (HTTPS exigé par Safari pour caméra et capteurs).

Tout est généré sur le PC, sans service externe. Le certificat racine (`ca.crt`) s'installe une fois
sur le téléphone (voir `docs/phone_setup.md`) ; le certificat serveur est régénéré automatiquement
si l'adresse IP locale change.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_NAME = "VisionAId CA locale"
SERVER_DAYS = 397  # iOS refuse les certificats serveur de plus de 398 jours
CA_DAYS = 3650


@dataclass
class CertPaths:
    """Chemins des fichiers générés."""

    ca_cert: Path
    ca_key: Path
    server_cert: Path
    server_key: Path


def local_ips() -> list[str]:
    """Adresses IPv4 locales probables (interface par défaut + résolutions du nom d'hôte)."""
    ips: set[str] = {"127.0.0.1"}
    try:  # interface de sortie par défaut, sans envoyer de paquet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ips)


def host_names() -> list[str]:
    """Noms DNS couverts par le certificat serveur."""
    h = socket.gethostname().split(".")[0]
    names = {"localhost", h, f"{h}.local"}
    return sorted(n for n in names if n)


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_key(key, path: Path) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def make_ca(paths: CertPaths) -> None:
    """Crée l'autorité de certification locale."""
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME)])
    now = _now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(key, paths.ca_key)
    paths.ca_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def make_server_cert(paths: CertPaths, names: list[str], ips: list[str]) -> None:
    """Émet le certificat serveur signé par l'autorité locale."""
    ca_key = serialization.load_pem_private_key(paths.ca_key.read_bytes(), None)
    ca_cert = x509.load_pem_x509_certificate(paths.ca_cert.read_bytes())
    key = _key()
    now = _now()
    san = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_cert_sign=False,
                crl_sign=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(key, paths.server_key)
    paths.server_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def server_cert_covers(paths: CertPaths, names: list[str], ips: list[str]) -> bool:
    """Vrai si le certificat serveur existe, n'expire pas sous 7 jours et couvre noms et IP."""
    if not paths.server_cert.exists() or not paths.server_key.exists():
        return False
    cert = x509.load_pem_x509_certificate(paths.server_cert.read_bytes())
    if cert.not_valid_after_utc < _now() + dt.timedelta(days=7):
        return False
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    have_dns = set(san.get_values_for_type(x509.DNSName))
    have_ip = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    return set(names) <= have_dns and set(ips) <= have_ip


def ensure_certs(
    directory: str | Path, names: list[str] | None = None, ips: list[str] | None = None
) -> CertPaths:
    """Crée l'autorité si besoin et (ré)émet le certificat serveur s'il ne couvre plus l'hôte."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    paths = CertPaths(d / "ca.crt", d / "ca.key", d / "server.crt", d / "server.key")
    names = names or host_names()
    ips = ips or local_ips()
    if not paths.ca_cert.exists() or not paths.ca_key.exists():
        make_ca(paths)
        for p in (paths.server_cert, paths.server_key):
            p.unlink(missing_ok=True)
    if not server_cert_covers(paths, names, ips):
        make_server_cert(paths, names, ips)
    return paths


def server_ssl_context(paths: CertPaths) -> ssl.SSLContext:
    """Contexte TLS côté serveur."""
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(str(paths.server_cert), str(paths.server_key))
    return ctx


def client_ssl_context(paths: CertPaths) -> ssl.SSLContext:
    """Contexte TLS d'un client qui fait confiance à l'autorité locale (faux téléphone, tests)."""
    ctx = ssl.create_default_context(cafile=str(paths.ca_cert))
    return ctx
