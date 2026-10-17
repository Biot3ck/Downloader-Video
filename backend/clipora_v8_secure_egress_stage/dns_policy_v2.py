import dns.exception
import dns.resolver

from ip_policy import validate_destination_ip

DNS_TIMEOUT = 1
DNS_LIFETIME = 3


def resolve_safe_host_v2(hostname):
    resolver = dns.resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT
    resolver.lifetime = DNS_LIFETIME

    addresses = []

    for record_type in ("A", "AAAA"):
        try:
            answers = resolver.resolve(hostname, record_type)
        except dns.resolver.NoAnswer:
            continue
        except dns.resolver.NXDOMAIN as exc:
            # A contradictory A/AAAA response must not preserve a partial answer.
            raise ValueError("DNS name does not exist") from exc
        except dns.exception.DNSException as exc:
            raise ValueError("DNS resolution failed") from exc

        addresses.extend(str(answer) for answer in answers)

    if not addresses:
        raise ValueError("No DNS addresses found")

    validated = [
        validate_destination_ip(address)
        for address in addresses
    ]

    return sorted(set(validated))
