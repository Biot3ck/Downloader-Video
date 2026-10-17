from connect_policy import validate_connect_target
from dns_policy_v2 import resolve_safe_host_v2


def validate_destination(target):
    host, port = validate_connect_target(target)

    addresses = resolve_safe_host_v2(host)

    if not addresses:
        raise ValueError("No safe destination addresses")

    return {
        "host": host,
        "port": port,
        "addresses": addresses,
    }
