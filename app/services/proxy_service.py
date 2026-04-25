from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class ProxyService:
    def __init__(self, proxy_file: Path = Path("proxies.txt")):
        self.proxy_file = proxy_file
        self.proxies: List[str] = []
        self.current_proxy: Optional[str] = None
        
    async def load_proxies(self) -> None:
        """Загружает прокси из файла."""
        if not self.proxy_file.exists():
            logger.warning(f"Proxy file {self.proxy_file} not found")
            return
        
        try:
            # Пробуем разные кодировки
            encodings = ['utf-8', 'cp1251', 'latin-1']
            for encoding in encodings:
                try:
                    with open(self.proxy_file, 'r', encoding=encoding) as f:
                        self.proxies = [line.strip() for line in f if line.strip()]
                    logger.info(f"Loaded {len(self.proxies)} proxies from {self.proxy_file} using {encoding}")
                    return
                except UnicodeDecodeError:
                    continue
            
            logger.error(f"Failed to read proxy file {self.proxy_file} with any encoding")
        except Exception as e:
            logger.error(f"Error loading proxies: {e}")
    
    async def check_proxy(self, proxy: str, timeout: int = 5) -> bool:
        """Проверяет работоспособность прокси."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.telegram.org/",
                    proxy=proxy,
                    timeout=timeout
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"Proxy {proxy} failed: {e}")
            return False
    
    async def find_working_proxy(self) -> Optional[str]:
        """Ищет рабочий прокси."""
        if not self.proxies:
            await self.load_proxies()
            if not self.proxies:
                return None
        
        tasks = []
        for proxy in self.proxies:
            task = asyncio.create_task(self.check_proxy(proxy))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for proxy, result in zip(self.proxies, results):
            if result is True:
                logger.info(f"Found working proxy: {proxy}")
                self.current_proxy = proxy
                return proxy
        
        logger.warning("No working proxies found")
        return None
    
    def get_current_proxy(self) -> Optional[str]:
        """Возвращает текущий рабочий прокси."""
        return self.current_proxy
    
    async def rotate_proxy(self) -> Optional[str]:
        """Пробует найти новый рабочий прокси."""
        self.current_proxy = None
        return await self.find_working_proxy()