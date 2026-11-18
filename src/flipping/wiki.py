"""Thin client for the OSRS Wiki real-time prices API.

Docs: https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices
Only bulk endpoints are used (one request covers every item), per the wiki's
acceptable-use guidance.
"""

import httpx

from .config import settings


class WikiClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.api_base,
            headers={"User-Agent": settings.user_agent},
            timeout=30,
        )

    async def _get(self, path: str, **params) -> dict | list:
        r = await self._http.get(path, params=params or None)
        r.raise_for_status()
        return r.json()

    async def mapping(self) -> list[dict]:
        return await self._get("/mapping")

    async def latest(self) -> dict[str, dict]:
        return (await self._get("/latest"))["data"]

    async def window(self, step: int, timestamp: int | None = None) -> tuple[int, dict[str, dict]]:
        """Averages/volumes for every item over one window.

        step: 300 (/5m) or 3600 (/1h). timestamp: window start, which must be
        divisible by step; omit for the newest available window.
        Returns (window start timestamp, {item_id: averages/volumes}).
        """
        path = {300: "/5m", 3600: "/1h"}[step]
        params = {"timestamp": timestamp} if timestamp is not None else {}
        body = await self._get(path, **params)
        return body["timestamp"], body["data"]

    async def aclose(self) -> None:
        await self._http.aclose()
