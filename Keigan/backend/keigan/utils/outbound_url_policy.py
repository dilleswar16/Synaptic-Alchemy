"""Which URLs Keigan may call on behalf of a user (SSRF protection, finding V16).

Users type endpoint URLs (log tools, synthetic probes). Keigan runs inside the corporate network with its own identity, so a URL
that points at a cluster service, a loopback or link-local address (the cloud metadata service) or a private network would turn
Keigan into a proxy for the user. The policy accepts only ``https`` URLs without embedded credentials whose host is public after
DNS resolution. Platform admins can allow named internal hosts (for example an on-premises Splunk) and deny host suffixes.

The DNS resolver is injected so the policy can be tested without a network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from keigan.exceptions.keigan_exceptions import BusinessValidationException

HostnameResolver = Callable[[str], Awaitable[list[str]]]

NOT_HTTPS_MESSAGE = "Use an https:// address."
EMBEDDED_CREDENTIALS_MESSAGE = "Remove the user name and password from the address."
INTERNAL_ADDRESS_MESSAGE = "This address points at a private or internal network, which Keigan does not call."
UNRESOLVABLE_HOST_MESSAGE = "Keigan could not find this host name. Check the address."
MISSING_HOST_MESSAGE = "The address has no host name."


class OutboundUrlRejectedError(BusinessValidationException):
    """The URL breaks the outbound policy. ``reason`` is the end-user message."""

    def __init__(self, reason: str, field_name: str | None = None):
        super().__init__(
            f"The address is not allowed: {reason}",
            field_errors=[{"field": field_name, "message": reason}] if field_name else None,
        )
        self.reason = reason


async def resolve_hostname_addresses(hostname: str) -> list[str]:
    """All IP addresses the system resolver returns for the host (empty when it does not resolve)."""
    try:
        address_records = await asyncio.get_running_loop().getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return sorted({str(record[4][0]) for record in address_records})


def _matches_host_rule(hostname: str, rule: str) -> bool:
    """A rule ``example.com`` matches that host only; ``.example.com`` matches its sub-domains."""
    return hostname.endswith(rule) if rule.startswith(".") else hostname == rule


def _is_public_address(address_text: str) -> bool:
    address = ipaddress.ip_address(address_text.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


class OutboundUrlPolicy:
    def __init__(
        self,
        *,
        allowed_hosts: tuple[str, ...] = (),
        denied_host_suffixes: tuple[str, ...] = (),
        resolves_hostnames: bool = True,
        resolver: HostnameResolver = resolve_hostname_addresses,
    ):
        """``resolves_hostnames=False`` skips DNS (simulated mode never makes a request); literal IP addresses are still checked."""
        self.allowed_hosts = tuple(host.lower() for host in allowed_hosts)
        self.denied_host_suffixes = tuple(suffix.lower() for suffix in denied_host_suffixes)
        self.resolves_hostnames = resolves_hostnames
        self.resolver = resolver

    async def ensure_allowed(self, url: str, field_name: str | None = None) -> None:
        """Raise :class:`OutboundUrlRejectedError` (422, with a field error when ``field_name`` is given) unless Keigan may call the URL."""
        try:
            await self._check(url)
        except OutboundUrlRejectedError as rejection:
            raise OutboundUrlRejectedError(rejection.reason, field_name) from None

    async def _check(self, url: str) -> None:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() != "https":
            raise OutboundUrlRejectedError(NOT_HTTPS_MESSAGE)
        if parts.username is not None or parts.password is not None:
            raise OutboundUrlRejectedError(EMBEDDED_CREDENTIALS_MESSAGE)
        try:
            hostname = (parts.hostname or "").lower().rstrip(".")
        except ValueError as invalid_address:
            raise OutboundUrlRejectedError(MISSING_HOST_MESSAGE) from invalid_address
        if not hostname:
            raise OutboundUrlRejectedError(MISSING_HOST_MESSAGE)
        if any(_matches_host_rule(hostname, suffix) for suffix in self.denied_host_suffixes):
            raise OutboundUrlRejectedError(INTERNAL_ADDRESS_MESSAGE)
        is_allow_listed = any(_matches_host_rule(hostname, rule) for rule in self.allowed_hosts)
        for address_text in await self._addresses_of(hostname):
            if not is_allow_listed and not _is_public_address(address_text):
                raise OutboundUrlRejectedError(INTERNAL_ADDRESS_MESSAGE)

    async def _addresses_of(self, hostname: str) -> list[str]:
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            if not self.resolves_hostnames:
                return []
            resolved_addresses = await self.resolver(hostname)
            if not resolved_addresses:
                raise OutboundUrlRejectedError(UNRESOLVABLE_HOST_MESSAGE) from None
            return resolved_addresses
        return [hostname]
