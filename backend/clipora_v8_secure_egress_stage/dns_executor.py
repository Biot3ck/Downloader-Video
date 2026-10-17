import asyncio
from concurrent.futures import ThreadPoolExecutor

from destination_policy import validate_destination

MAX_DNS_WORKERS = 8
DNS_TIMEOUT = 3

executor = ThreadPoolExecutor(
    max_workers=MAX_DNS_WORKERS,
    thread_name_prefix="clipora-dns",
)

slots = asyncio.Semaphore(MAX_DNS_WORKERS)


class DNSTimeoutError(Exception):
    pass


async def resolve_destination(target):
    try:
        await asyncio.wait_for(slots.acquire(), timeout=DNS_TIMEOUT)
    except asyncio.TimeoutError as exc:
        raise DNSTimeoutError("DNS capacity wait timed out") from exc

    loop = asyncio.get_running_loop()

    try:
        future = loop.run_in_executor(
            executor,
            validate_destination,
            target,
        )
    except BaseException:
        slots.release()
        raise

    def release_slot(done):
        slots.release()

    future.add_done_callback(release_slot)

    try:
        return await asyncio.wait_for(
            asyncio.shield(future),
            timeout=DNS_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise DNSTimeoutError(
            "DNS resolution timed out"
        ) from exc
