import ipaddress
import re

HOST_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$"
)


def validate_connect_target(target):
    if not isinstance(target, str):
        raise ValueError("Invalid target")

    if len(target) > 255:
        raise ValueError("Target too long")

    if target.count(":") != 1:
        raise ValueError("Invalid CONNECT authority")

    host, port = target.rsplit(":", 1)

    if port != "443":
        raise ValueError("Only HTTPS port 443 is allowed")

    if not host or not HOST_RE.fullmatch(host):
        raise ValueError("Invalid hostname")

    # Reject alternate numeric forms and ambiguous DNS names before resolution.
    labels = host.lower().split('.')
    if (len(labels) < 2 or len(host) > 253
            or any(not label or len(label) > 63 or not label[0].isalnum()
                   or not label[-1].isalnum()
                   or any(not (c.isascii() and (c.isalnum() or c == '-')) for c in label)
                   for label in labels)
            or not any(c.isalpha() for c in labels[-1])):
        raise ValueError("Invalid hostname")

    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("Local hostname blocked")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal targets blocked")

    return host.lower(), 443
