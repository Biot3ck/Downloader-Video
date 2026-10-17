import ipaddress


def validate_destination_ip(value):
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError("Invalid IP address")

    if not ip.is_global:
        raise ValueError("Non-public IP blocked")

    if ip.is_multicast:
        raise ValueError("Multicast IP blocked")

    if ip.is_reserved:
        raise ValueError("Reserved IP blocked")

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return validate_destination_ip(
            str(ip.ipv4_mapped)
        )

    return str(ip)
