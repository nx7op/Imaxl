"""
saavn.py — Thin async client for JioSaavn API.
"""

import asyncio
import html
import logging
import re
from typing import Optional

import httpx

from config import SAAVN_API_BASE, HTTP_TIMEOUT

logger = logging.getLogger("saavn-bot.saavn")


def clean_html(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def best_download_url(download_urls: list[dict]) -> Optional[str]:
    if not download_urls:
        return None
    quality_order = ["320kbps", "160kbps", "96kbps", "48kbps", "12kbps"]
    by_quality = {d.get("quality"): d.get("url") for d in download_urls}
    for q in quality_order:
        if by_quality.get(q):
            return by_quality[q]
    return download_urls[-1].get("url")


def format_duration(seconds) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "?:??"
    return f"{seconds // 60}:{seconds % 60:02d}"


class Track:
    __slots__ = ("id", "title", "artist", "album", "duration", "url", "thumb")

    def __init__(self, id_, title, artist, album, duration, url, thumb):
        self.id = id_
        self.title = title
        self.artist = artist
        self.album = album
        self.duration = duration
        self.url = url
        self.thumb = thumb

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration)

    @classmethod
    def from_api_song(cls, song: dict) -> Optional["Track"]:
        song_id = song.get("id")
        url = best_download_url(song.get("downloadUrl", []))
        if not song_id or not url:
            return None

        title = clean_html(song.get("name") or "Unknown Title")
        artists = song.get("artists", {}).get("primary", []) or []
        artist = ", ".join(clean_html(a.get("name", "")) for a in artists) or "Unknown Artist"
        album = clean_html((song.get("album") or {}).get("name") or "")

        duration = song.get("duration")
        try:
            duration = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration = None

        images = song.get("image", []) or []
        thumb = None
        for q in ("500x500", "150x150", "50x50"):
            match = next((i.get("url") for i in images if i.get("quality") == q), None)
            if match:
                thumb = match
                break

        return cls(song_id, title, artist, album, duration, url, thumb)


class SaavnClient:
    def __init__(self, base_url: str = SAAVN_API_BASE, timeout: float = HTTP_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self._client.aclose()

    async def search(self, query: str, limit: int = 10, retries: int = 2) -> list[Track]:
        url = f"{self.base_url}/api/search/songs"
        params = {"query": query, "limit": limit}

        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success"):
                    return []
                songs = data.get("data", {}).get("results", []) or []
                tracks = [Track.from_api_song(s) for s in songs]
                return [t for t in tracks if t is not None]
            except (httpx.HTTPError, ValueError) as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
        logger.warning("Saavn search failed for %r: %s", query, last_error)
        return []

    async def get_first_result(self, query: str) -> Optional[Track]:
        results = await self.search(query, limit=1)
        return results[0] if results else None
