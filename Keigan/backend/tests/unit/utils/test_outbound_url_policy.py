"""keigan/utils/outbound_url_policy.py: which URLs Keigan may call on behalf of a user (V16 SSRF protection)."""

from __future__ import annotations

import pytest

from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.utils.outbound_url_policy import OutboundUrlPolicy

PRIVATE_ADDRESS_MESSAGE = "This address points at a private or internal network, which Keigan does not call."


def build_policy(
    addresses_by_host: dict[str, list[str]] | None = None,
    *,
    allowed_hosts: tuple[str, ...] = (),
    denied_host_suffixes: tuple[str, ...] = (".svc", ".cluster.local", ".internal", "localhost"),
    resolves_hostnames: bool = True,
) -> OutboundUrlPolicy:
    known_addresses = addresses_by_host or {}

    async def fake_resolver(hostname: str) -> list[str]:
        return known_addresses.get(hostname, [])

    return OutboundUrlPolicy(
        allowed_hosts=allowed_hosts, denied_host_suffixes=denied_host_suffixes, resolves_hostnames=resolves_hostnames, resolver=fake_resolver
    )


async def rejection_message(policy: OutboundUrlPolicy, url: str) -> str:
    with pytest.raises(BusinessValidationException) as rejection:
        await policy.ensure_allowed(url, field_name="endpointUrl")
    assert rejection.value.extra["fieldErrors"][0]["field"] == "endpointUrl"
    return rejection.value.extra["fieldErrors"][0]["message"]


async def test_public_https_host_is_allowed() -> None:
    policy = build_policy({"elastic.example.com": ["93.184.216.34"]})
    await policy.ensure_allowed("https://elastic.example.com:9243/")


@pytest.mark.parametrize("url", ["http://elastic.example.com", "ftp://elastic.example.com", "elastic.example.com", "//elastic.example.com"])
async def test_anything_but_https_is_rejected(url: str) -> None:
    message = await rejection_message(build_policy({"elastic.example.com": ["93.184.216.34"]}), url)
    assert message == "Use an https:// address."


async def test_credentials_inside_the_url_are_rejected() -> None:
    message = await rejection_message(build_policy({"elastic.example.com": ["93.184.216.34"]}), "https://user:secret@elastic.example.com")
    assert message == "Remove the user name and password from the address."


@pytest.mark.parametrize(
    "address",
    ["10.1.2.3", "172.16.0.9", "192.168.1.1", "127.0.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "[::1]", "[fe80::1]", "[fd00::5]", "[::ffff:10.0.0.1]"],
)
async def test_private_loopback_and_link_local_ip_literals_are_rejected(address: str) -> None:
    assert await rejection_message(build_policy(), f"https://{address}/") == PRIVATE_ADDRESS_MESSAGE


async def test_host_name_that_resolves_to_a_private_address_is_rejected() -> None:
    policy = build_policy({"sneaky.example.com": ["10.0.0.7"]})
    assert await rejection_message(policy, "https://sneaky.example.com") == PRIVATE_ADDRESS_MESSAGE


async def test_host_name_is_rejected_when_any_resolved_address_is_private() -> None:
    policy = build_policy({"mixed.example.com": ["93.184.216.34", "169.254.169.254"]})
    assert await rejection_message(policy, "https://mixed.example.com") == PRIVATE_ADDRESS_MESSAGE


@pytest.mark.parametrize("host", ["kubernetes.default.svc", "vault.keigan.svc.cluster.local", "metadata.google.internal", "localhost"])
async def test_cluster_internal_and_local_host_names_are_rejected_even_if_they_resolve_publicly(host: str) -> None:
    assert await rejection_message(build_policy({host: ["93.184.216.34"]}), f"https://{host}/") == PRIVATE_ADDRESS_MESSAGE


async def test_host_that_cannot_be_resolved_is_rejected() -> None:
    assert await rejection_message(build_policy(), "https://no-such-host.example.com") == "Keigan could not find this host name. Check the address."


async def test_allow_listed_host_may_resolve_to_a_private_address() -> None:
    policy = build_policy({"splunk.corp.example.com": ["10.20.30.40"]}, allowed_hosts=("splunk.corp.example.com",))
    await policy.ensure_allowed("https://splunk.corp.example.com:8089")


async def test_allow_list_suffix_covers_sub_domains() -> None:
    policy = build_policy({"a.logs.corp.example.com": ["10.20.30.40"]}, allowed_hosts=(".logs.corp.example.com",))
    await policy.ensure_allowed("https://a.logs.corp.example.com")


async def test_denied_suffix_wins_over_the_allow_list() -> None:
    policy = build_policy(allowed_hosts=("vault.keigan.svc.cluster.local",))
    assert await rejection_message(policy, "https://vault.keigan.svc.cluster.local") == PRIVATE_ADDRESS_MESSAGE


async def test_without_dns_resolution_unknown_hosts_pass_but_private_literals_do_not() -> None:
    policy = build_policy(resolves_hostnames=False)
    await policy.ensure_allowed("https://demo-elastic.example.test")
    with pytest.raises(BusinessValidationException):
        await policy.ensure_allowed("https://10.0.0.1")


async def test_rejection_without_a_field_name_has_no_field_errors() -> None:
    with pytest.raises(BusinessValidationException) as rejection:
        await build_policy().ensure_allowed("http://x.example.com")
    assert rejection.value.detail == "The address is not allowed: Use an https:// address."
    assert rejection.value.extra["fieldErrors"] == []
