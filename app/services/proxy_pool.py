from __future__ import annotations

import itertools
from pathlib import Path
from urllib.parse import urlparse

SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5"}


class ProxyPool:
    def __init__(self, proxies: list[str | None]) -> None:
        if not proxies:
            proxies = [None]

        self._proxies = proxies
        self._cycle = itertools.cycle(proxies)
        self._current = next(self._cycle)

    @property
    def current(self) -> str | None:
        return self._current

    @property
    def size(self) -> int:
        return len(self._proxies)

    def rotate(self) -> str | None:
        self._current = next(self._cycle)
        return self._current


def load_proxy_pool(*, proxy_url: str | None, proxy_file: Path) -> ProxyPool:
    proxies: list[str | None] = []

    if proxy_url:
        proxies.append(proxy_url)

    if proxy_file.exists():
        proxies.extend(_read_proxy_file(proxy_file))

    return ProxyPool(_deduplicate(proxies))


def _read_proxy_file(proxy_file: Path) -> list[str]:
    proxies: list[str] = []
    for raw_line in proxy_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not _is_supported_proxy_url(line):
            continue
        proxies.append(line)
    return proxies


def _deduplicate(proxies: list[str | None]) -> list[str | None]:
    seen: set[str | None] = set()
    unique: list[str | None] = []
    for proxy in proxies:
        if proxy in seen:
            continue
        seen.add(proxy)
        unique.append(proxy)
    return unique


def _is_supported_proxy_url(proxy_url: str) -> bool:
    parsed = urlparse(proxy_url)
    return parsed.scheme in SUPPORTED_PROXY_SCHEMES and bool(parsed.hostname) and bool(parsed.port)
