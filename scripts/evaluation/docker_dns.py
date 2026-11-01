"""Parse the optional direct-gateway DNS override."""

import ipaddress


def parse_servers(value):
    servers = []
    for item in value.split(','):
        address = ipaddress.IPv4Address(item.strip())
        if address.is_loopback or address.is_multicast or address.is_unspecified or address.is_link_local:
            raise ValueError('CONTAINER_DNS requires reachable unicast IPv4 addresses')
        if str(address) not in servers:
            servers.append(str(address))
    return servers
