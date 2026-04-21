from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiohttp_socks import ProxyConnector

SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5"}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Check SOCKS/HTTP proxies against Telegram API.")
    parser.add_argument("--file", default="proxies.txt", help="Proxy list file.")
    parser.add_argument("--limit", type=int, default=30, help="How many proxies to test.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Request timeout in seconds.")
    parser.add_argument("--only-alive", action="store_true", help="Print only alive proxies.")
    args = parser.parse_args()

    proxies = _read_proxies(Path(args.file))[: args.limit]
    if not proxies:
        print("No proxies found.")
        return

    tasks = [_check_proxy(proxy, args.timeout) for proxy in proxies]
    results = await asyncio.gather(*tasks)
    alive = [proxy for proxy, ok, _ in results if ok]

    for proxy, ok, reason in results:
        if args.only_alive and not ok:
            continue
        status = "OK" if ok else "FAIL"
        print(_ascii(f"{status:4} {proxy} {reason}"))

    print(f"\nAlive: {len(alive)}/{len(proxies)}")
    if alive:
        print(f"First alive proxy: {alive[0]}")


def _read_proxies(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if _is_supported_proxy_url(line.strip())
    ]


async def _check_proxy(proxy: str, timeout: float) -> tuple[str, bool, str]:
    try:
        connector = ProxyConnector.from_url(proxy)
    except ValueError as error:
        return proxy, False, str(error)

    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
            async with session.get("https://api.telegram.org") as response:
                return proxy, response.status < 500, f"HTTP {response.status}"
    except Exception as error:
        message = str(error).splitlines()[0] if str(error).splitlines() else type(error).__name__
        return proxy, False, message


def _is_supported_proxy_url(proxy_url: str) -> bool:
    parsed = urlparse(proxy_url)
    return parsed.scheme in SUPPORTED_PROXY_SCHEMES and bool(parsed.hostname) and bool(parsed.port)


def _ascii(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii")


if __name__ == "__main__":
    asyncio.run(main())
