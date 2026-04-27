from __future__ import annotations

import ipaddress
import socket
from typing import Optional, Union
from urllib.parse import urlsplit

from src.services.exceptions import ValidationApiError


def validate_public_http_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = (parts.hostname or "").strip().lower()

    if parts.scheme not in {"http", "https"}:
        raise ValidationApiError("Only http and https product URLs are allowed.")

    if not hostname:
        raise ValidationApiError("Product URL must include a valid hostname.")

    if parts.username or parts.password:
        raise ValidationApiError("Product URL credentials are not allowed.")

    if hostname in {"localhost", "0.0.0.0"} or hostname.endswith(".local"):
        raise ValidationApiError("Local and private-network URLs are not allowed.")

    if "." not in hostname and hostname not in {"localhost"}:
        raise ValidationApiError("Product URL must use a public hostname.")

    _validate_hostname_target(hostname)
    return url


def _validate_hostname_target(hostname: str) -> None:
    literal = _maybe_ip_address(hostname)
    if literal is not None:
        _ensure_public_ip(literal)
        return

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return

    if not infos:
        return

    for info in infos:
        sockaddr = info[4]
        address = sockaddr[0]
        ip = _maybe_ip_address(address)
        if ip is None:
            continue
        _ensure_public_ip(ip)


def _maybe_ip_address(value: str) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _ensure_public_ip(ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise ValidationApiError("Local and private-network URLs are not allowed.")
