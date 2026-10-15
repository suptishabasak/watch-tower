"""SSRF protection: only public http(s) destinations may be monitored."""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    """Raised with a user-presentable message."""


ALLOWED_PORTS = {80, 443, 8080, 8443}
BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal", "instance-data"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".intranet", ".corp")

METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS / GCP / Azure
    ipaddress.ip_address("169.254.170.2"),  # AWS ECS task metadata
    ipaddress.ip_address("100.100.100.200"),  # Alibaba
    ipaddress.ip_address("fd00:ec2::254"),  # AWS IPv6
}
# Prefixes that can embed private IPv4 addresses
_EXTRA_BLOCKED = [ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("2002::/16")]

Resolver = Callable[[str], list]


def is_public_ip(ip) -> bool:
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip in METADATA_IPS:
        return False
    if any(ip in net for net in _EXTRA_BLOCKED):
        return False
    return ip.is_global and not ip.is_multicast


def resolve_host(host: str) -> list:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"The domain “{host}” could not be found.") from exc
    return [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]


def assert_public_host(host: str, resolver: Resolver = resolve_host) -> None:
    """Raise UnsafeURLError unless `host` is a public hostname/IP (every resolved address must be public)."""
    host = host.rstrip(".").lower()
    if not host:
        raise UnsafeURLError("That URL has no hostname.")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeURLError("Local and internal hostnames can't be monitored.")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError("Private, loopback and reserved IP addresses can't be monitored.")
        return

    if "." not in host:
        raise UnsafeURLError("Use a full domain name, such as example.com.")

    ips = resolver(host)
    if not ips:
        raise UnsafeURLError(f"The domain “{host}” could not be found.")
    if not all(is_public_ip(ip) for ip in ips):
        raise UnsafeURLError("That address points to a private or reserved network.")


def validate_public_url(url: str, resolver: Resolver = resolve_host) -> str:
    """Validate and normalise a user-supplied URL. Returns the URL to store."""
    url = (url or "").strip()
    if not url:
        raise UnsafeURLError("Enter a URL.")
    if len(url) > 2048:
        raise UnsafeURLError("That URL is too long.")
    if "://" not in url:
        url = "https://" + url

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise UnsafeURLError("That doesn't look like a valid URL.") from None

    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http:// and https:// URLs can be monitored.")
    if not parts.hostname:
        raise UnsafeURLError("That URL has no hostname.")
    if parts.username or parts.password:
        raise UnsafeURLError("URLs with embedded credentials aren't allowed.")
    if port is not None and port not in ALLOWED_PORTS:
        raise UnsafeURLError("Only ports 80, 443, 8080 and 8443 are allowed.")

    assert_public_host(parts.hostname, resolver)
    return url