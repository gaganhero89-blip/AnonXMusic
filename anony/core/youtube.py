# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import os
import re
import asyncio
import aiohttp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from anony import logger
from anony.helpers import Track, utils

# ── Fallen API config — .env se aata hai ────────────────────────────────────
API_KEY: str = os.getenv("API_KEY", "")
API_URL: str = os.getenv("API_URL", "https://tgmusic.fallenapi.fun").rstrip("/")
# ─────────────────────────────────────────────────────────────────────────────


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )
        self._headers = {"api-key": API_KEY}
        # Concurrent download lock — same video_id ke double download rokta hai
        self._locks: dict[str, asyncio.Lock] = {}

    # ── URL validators ────────────────────────────────────────────────────────

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        return bool(re.match(self.iregex, url))

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: str, m_id: int, video: bool = False) -> "Track | None":
        try:
            _search = VideosSearch(query, limit=1, with_live=False)
            results = await _search.next()
        except Exception:
            return None

        if not (results and results.get("result")):
            return None

        data = results["result"][0]
        thumbs = data.get("thumbnails") or [{}]
        return Track(
            id=data.get("id"),
            channel_name=data.get("channel", {}).get("name"),
            duration=data.get("duration"),
            duration_sec=utils.to_seconds(data.get("duration")),
            message_id=m_id,
            title=(data.get("title") or "")[:25],
            thumbnail=thumbs[-1].get("url", "").split("?")[0],
            url=data.get("link"),
            view_count=data.get("viewCount", {}).get("short"),
            video=video,
        )

    # ── Playlist ──────────────────────────────────────────────────────────────

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                thumbs = data.get("thumbnails") or [{}]
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=(data.get("title") or "")[:25],
                    thumbnail=thumbs[-1].get("url", "").split("?")[0],
                    url=(data.get("link") or "").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception:
            pass
        return tracks

    # ── Fallen API se download ────────────────────────────────────────────────

    async def _fallen_download(self, video_id: str, video: bool) -> "str | None":
        """
        Fallen API call karke direct file URL lao, phir file download karo.

        Expected API response:
        {
            "status": true,
            "data": {
                "url": "https://...direct-link...",
                "title": "...",
                ...
            }
        }
        """
        if not API_KEY:
            logger.warning("API_KEY set nahi hai — Fallen API kaam nahi karega.")
            return None

        yt_url = self.base + video_id
        media_type = "video" if video else "audio"
        endpoint = f"{API_URL}/youtube"

        params = {
            "url": yt_url,
            "type": media_type,   # "audio" ya "video"
        }

        ext = "mp4" if video else "m4a"
        save_path = f"downloads/{video_id}.{ext}"

        try:
            async with aiohttp.ClientSession(
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as session:

                # Step 1: API se direct download link lo
                async with session.get(endpoint, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Fallen API error: HTTP %s | video_id=%s", resp.status, video_id
                        )
                        return None
                    data = await resp.json()

                if not data.get("status"):
                    logger.warning("Fallen API: status=false | %s", data)
                    return None

                direct_url = data.get("data", {}).get("url")
                if not direct_url:
                    logger.warning("Fallen API: direct URL missing | %s", data)
                    return None

                # Step 2: Direct URL se actual file download karo
                async with session.get(direct_url) as file_resp:
                    file_resp.raise_for_status()
                    Path("downloads").mkdir(exist_ok=True)
                    with open(save_path, "wb") as f:
                        async for chunk in file_resp.content.iter_chunked(1024 * 64):
                            f.write(chunk)

        except asyncio.TimeoutError:
            logger.warning("Fallen API timeout | video_id=%s", video_id)
            return None
        except Exception as e:
            logger.warning("Fallen API download failed | video_id=%s | %s", video_id, e)
            return None

        return save_path if Path(save_path).exists() else None

    # ── Public download method ────────────────────────────────────────────────

    async def download(self, video_id: str, video: bool = False) -> "str | None":
        ext = "mp4" if video else "m4a"
        filename = f"downloads/{video_id}.{ext}"

        # Pehle se file hai toh skip
        if Path(filename).exists():
            return filename

        # Same video_id ke concurrent requests ko serialize karo
        if video_id not in self._locks:
            self._locks[video_id] = asyncio.Lock()

        async with self._locks[video_id]:
            # Lock ke andar dobara check — race condition fix
            if Path(filename).exists():
                return filename

            result = await self._fallen_download(video_id, video)

        # Lock cleanup
        self._locks.pop(video_id, None)
        return result
                
