import asyncio
from typing import Optional
import httpx
from contextlib import asynccontextmanager

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        
    @asynccontextmanager
    async def get_client(self):
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=30.0,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                )
            try:
                yield self._client
            except Exception as e:
                await self._client.aclose()
                self._client = None
                raise e 