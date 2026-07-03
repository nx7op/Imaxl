#!/usr/bin/env python3
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⚡ IMAXL VC MUSIC BOT — Ultimate Edition v4.1 ⚡
  Voice Chat Music | 4K Video | HQ Audio | Real FX | AI Smart
  Owner: @stillrahul
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

# ── Pyrogram ───────────────────────────────────────
try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import (
        CallbackQuery,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Message,
    )
except ImportError:
    sys.exit("❌ pyrofork missing: pip install pyrofork")

# ── PyTgCalls ──────────────────────────────────────
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality, VideoQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("❌ py-tgcalls missing: pip install py-tgcalls")

# ── yt-dlp ─────────────────────────────────────────
import yt_dlp

# ═══════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════
IS_RAILWAY = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RAILWAY_PROJECT_ID")
    or os.environ.get("RAILWAY_SERVICE_ID")
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"❌ Missing required env var: {name}")
    return val


API_ID = int(_required("API_ID"))
API_HASH = _required("API_HASH")
BOT_TOKEN = _required("BOT_TOKEN")
SESSION_STRING = _required("SESSION_STRING")

SAAVN_API_BASE = os.environ.get("SAAVN_API_BASE", "https://saavn.sumit.co").rstrip("/")
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "@stillrahul")
OWNER_ID = _env_int("OWNER_ID", 0)
SUDO_USERS = {
    int(x) for x in os.environ.get("SUDO_USERS", "").replace(" ", "").split(",") if x.isdigit()
}
if OWNER_ID:
    SUDO_USERS.add(OWNER_ID)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")
MAX_QUEUE_SIZE = _env_int("MAX_QUEUE_SIZE", 50)
AUTO_LEAVE_SECONDS = _env_int("AUTO_LEAVE_SECONDS", 180)
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "15"))
BOT_TAGLINE = "⚡ IMAXL VC Music"

AUDIO_QUALITY = os.environ.get("AUDIO_QUALITY", "STUDIO").upper()
VIDEO_QUALITY = os.environ.get("VIDEO_QUALITY", "FHD_1080p").upper()

_AI_API_BASE = os.environ.get("AI_API_BASE", "https://gemini.adi7ya.workers.dev/?q=")

# ═══════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("imaxl")

# ═══════════════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════════════
bot = Client(
    "vc_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)

assistant = Client(
    "vc_assistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True,
)

calls = PyTgCalls(assistant)

# ═══════════════════════════════════════════════════
# QUALITY MAPS
# ═══════════════════════════════════════════════════
_AUDIO_Q_MAP = {
    "STUDIO": AudioQuality.STUDIO,
    "HIGH": AudioQuality.HIGH,
    "MEDIUM": AudioQuality.MEDIUM,
    "LOW": AudioQuality.LOW,
}
_AUDIO_QUALITY = _AUDIO_Q_MAP.get(AUDIO_QUALITY, AudioQuality.STUDIO)

_VIDEO_Q_MAP = {
    "UHD_4K": VideoQuality.UHD_4K,
    "FHD_1080P": VideoQuality.FHD_1080p,
    "HD_720P": VideoQuality.HD_720p,
    "SD_480P": VideoQuality.SD_480p,
}
_VIDEO_QUALITY = _VIDEO_Q_MAP.get(VIDEO_QUALITY, VideoQuality.FHD_1080p)

# ═══════════════════════════════════════════════════
# DSP EFFECTS — REAL FFMPEG FILTERS  
# ═══════════════════════════════════════════════════
_DSP_FILTERS = {
    "standard": "",
    "slowed": "atempo=0.85",
    "reverb": "aecho=0.8:0.9:1000|1800:0.3|0.25",
    "slowed_reverb": "atempo=0.85,aecho=0.8:0.9:1000|1800:0.3|0.25",
    "nightcore": "asetrate=48000*1.25,aresample=48000",
    "bassboost": "bass=g=12",
    "8d": "apulsator=hz=0.5",
    "vaporwave": "asetrate=48000*0.85,aresample=48000",
    "lofi": "atempo=0.92,lowpass=f=2500,highpass=f=150",
}

_DSP_NAMES = {
    "standard": "🎵 Standard",
    "slowed": "🐌 Slowed",
    "reverb": "🌊 Reverb",
    "slowed_reverb": "🌌 Slowed + Reverb",
    "nightcore": "⚡ Nightcore",
    "bassboost": "🔊 Bass Boost",
    "8d": "🎧 8D Audio",
    "vaporwave": "🌴 Vaporwave",
    "lofi": "📻 Lo-Fi",
}

# ═══════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════
DEFAULT_THUMB = "https://telegra.ph/file/default_music_thumb.jpg"
NOW_MSG: dict[int, int] = {}
OWNER_TAG = f"<b>{OWNER_USERNAME}</b>"

# ═══════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════
def is_sudo(msg: Message) -> bool:
    u = msg.from_user
    if not u:
        return False
    oid = OWNER_ID
    return (oid and u.id == oid) or u.id in SUDO_USERS


def uname(msg: Message) -> str:
    u = msg.from_user
    if not u:
        return "Unknown"
    return u.first_name or (f"@{u.username}" if u.username else "User")


async def auto_del(msg: Message, delay: float = 0.3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


async def safe_edit(msg, text: str, markup=None):
    try:
        if hasattr(msg, "edit_caption"):
            await msg.edit_caption(caption=text, reply_markup=markup)
        elif hasattr(msg, "edit_text"):
            await msg.edit_text(text, reply_markup=markup)
    except Exception:
        pass


async def safe_del(msg):
    try:
        await msg.delete()
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# COOKIES
# ═══════════════════════════════════════════════════
COOKIES_PATH: Optional[str] = None


def find_cookies() -> Optional[str]:
    global COOKIES_PATH
    paths = [
        "cookies.txt",
        "/app/cookies.txt",
        "/mnt/cookies.txt",
        "/data/cookies.txt",
        os.path.join(os.path.dirname(__file__), "cookies.txt"),
    ]
    for p in paths:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 50:
                COOKIES_PATH = p
                logger.info(f"🍪 Cookies loaded: {p}")
                return p
        except Exception:
            pass
    logger.warning("⚠️ No cookies.txt found")
    return None


find_cookies()


# ═══════════════════════════════════════════════════
# YOUTUBE URL CLEANER
# ═══════════════════════════════════════════════════
def clean_yt_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        if "youtu.be" in parsed.netloc:
            vid = parsed.path.strip("/").split("/")[0]
            if len(vid) == 11:
                return f"https://www.youtube.com/watch?v={vid}"
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
            m = re.search(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})", parsed.path)
            if m:
                return f"https://www.youtube.com/watch?v={m.group(1)}"
    except Exception:
        pass
    return url


# ═══════════════════════════════════════════════════
# SAAVN CLIENT
# ═══════════════════════════════════════════════════
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


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    duration: Optional[int]
    url: str
    thumb: Optional[str]
    is_video: bool = False

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

        return cls(song_id, title, artist, album, duration, url, thumb, False)


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
        logger.warning("Saavn search failed for %r: %s", query, last_error)
        return []

    async def get_first_result(self, query: str) -> Optional[Track]:
        results = await self.search(query, limit=1)
        return results[0] if results else None


saavn = SaavnClient()


# ═══════════════════════════════════════════════════
# YOUTUBE ENGINE — Multi-Strategy (FIXED)
# ═══════════════════════════════════════════════════
class YT:
    STRATEGIES = [
        {"name": "tv_embedded", "args": {"youtube": {"player_client": ["tv_embedded"], "player_skip": ["webpage", "js"]}}, "cookies": True},
        {"name": "web_creator", "args": {"youtube": {"player_client": ["web_creator"]}}, "cookies": True},
        {"name": "mweb", "args": {"youtube": {"player_client": ["mweb"]}}, "cookies": True},
        {"name": "default", "args": {}, "cookies": False},
        {"name": "android", "args": {"youtube": {"player_client": ["android"]}}, "cookies": False},
        {"name": "ios", "args": {"youtube": {"player_client": ["ios"]}}, "cookies": False},
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.youtube.com/",
    }

    @classmethod
    def _opts(cls, strat: dict, fmt: str) -> dict:
        o = {
            "format": fmt,
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 3,
            "cachedir": False,
            "source_address": "0.0.0.0",
            "http_headers": cls.HEADERS,
            "headers": cls.HEADERS,
        }
        if strat.get("args"):
            o["extractor_args"] = strat["args"]
        if strat.get("cookies") and COOKIES_PATH:
            o["cookiefile"] = COOKIES_PATH
            o["cookiesfrombrowser"] = None
        return o

    @classmethod
    def _extract(cls, query: str, video: bool = False) -> Optional[dict]:
        if "youtu" in query:
            query = clean_yt_url(query)

        fmt = "best[height>=1080]/best[height>=720]/best" if video else "bestaudio[abr>=128]/bestaudio/best"

        for strat in cls.STRATEGIES:
            try:
                t0 = time.time()
                with yt_dlp.YoutubeDL(cls._opts(strat, fmt)) as ydl:
                    info = ydl.extract_info(query, download=False)
                elapsed = round(time.time() - t0, 2)

                if not info:
                    continue
                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        continue
                    info = entries[0]
                if not info.get("url"):
                    continue

                logger.info(f"✅ [{elapsed}s] {strat['name']} -> {info.get('title', '?')[:40]}")
                return info
            except Exception as e:
                logger.debug(f"❌ {strat['name']}: {str(e)[:80]}")
                continue
        return None

    @classmethod
    async def track(cls, query: str, video: bool = False) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query, video)
        if not info:
            return None

        dur = int(info.get("duration") or 0) if info.get("duration") else 0

        thumb = DEFAULT_THUMB
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            best = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0))
            thumb = best.get("url", DEFAULT_THUMB)

        title = clean_html(info.get("title") or "Unknown")
        artist = clean_html(info.get("uploader") or "YouTube")

        # FIX: id_ -> id (Track dataclass field name)
        return Track(
            id=info.get("id", ""),
            title=title,
            artist=artist,
            album="YouTube",
            duration=dur,
            url=info["url"],
            thumb=thumb,
            is_video=video,
        )


# ═══════════════════════════════════════════════════
# QUEUE MANAGER
# ═══════════════════════════════════════════════════
@dataclass
class QueueItem:
    track: Track
    requested_by: str
    added_at: float = field(default_factory=time.time)


@dataclass
class ChatState:
    queue: list[QueueItem] = field(default_factory=list)
    current: Optional[QueueItem] = None
    is_playing: bool = False
    is_paused: bool = False
    loop: bool = False
    last_activity: float = field(default_factory=time.time)
    ai_autoplay: bool = True
    dsp_mode: str = "standard"
    volume: int = 100

    def touch(self):
        self.last_activity = time.time()


class QueueManager:
    def __init__(self, max_queue_size: int = 50):
        self.max_queue_size = max_queue_size
        self._chats: dict[int, ChatState] = {}

    def get(self, chat_id: int) -> ChatState:
        if chat_id not in self._chats:
            self._chats[chat_id] = ChatState()
        return self._chats[chat_id]

    def add(self, chat_id: int, track: Track, requested_by: str) -> tuple[bool, int]:
        state = self.get(chat_id)
        state.touch()
        item = QueueItem(track=track, requested_by=requested_by)

        if not state.is_playing and state.current is None:
            state.current = item
            state.is_playing = True
            return True, 0

        if len(state.queue) >= self.max_queue_size:
            return False, -1

        state.queue.append(item)
        return True, len(state.queue)

    def add_sync(self, chat_id: int, track: Track, requested_by: str) -> tuple[bool, int]:
        return self.add(chat_id, track, requested_by)

    def next(self, chat_id: int) -> Optional[QueueItem]:
        state = self.get(chat_id)
        state.touch()

        if state.loop and state.current is not None:
            return state.current

        if state.queue:
            state.current = state.queue.pop(0)
            return state.current

        state.current = None
        state.is_playing = False
        return None

    def clear(self, chat_id: int):
        state = self.get(chat_id)
        state.queue.clear()
        state.current = None
        state.is_playing = False
        state.is_paused = False
        state.loop = False

    def remove_at(self, chat_id: int, index: int) -> Optional[QueueItem]:
        state = self.get(chat_id)
        if 1 <= index <= len(state.queue):
            return state.queue.pop(index - 1)
        return None

    def shuffle(self, chat_id: int):
        random.shuffle(self.get(chat_id).queue)

    def toggle_ai(self, chat_id: int) -> bool:
        state = self.get(chat_id)
        state.ai_autoplay = not state.ai_autoplay
        return state.ai_autoplay

    def set_dsp(self, chat_id: int, mode: str):
        state = self.get(chat_id)
        if mode in _DSP_FILTERS:
            state.dsp_mode = mode

    def cleanup_idle(self, idle_seconds: float) -> list[int]:
        now = time.time()
        return [
            cid for cid, state in self._chats.items()
            if not state.is_playing and not state.queue
            and (now - state.last_activity) > idle_seconds
        ]

    def forget(self, chat_id: int):
        self._chats.pop(chat_id, None)


queues = QueueManager(max_queue_size=MAX_QUEUE_SIZE)


# ═══════════════════════════════════════════════════
# TRACK FINDER
# ═══════════════════════════════════════════════════
async def find_track(query: str, video: bool = False) -> Optional[Track]:
    # YouTube URL direct
    if "youtu" in query or query.startswith("http"):
        track = await YT.track(query, video=video)
        if track:
            return track
        # Fallback: try without video flag
        if video:
            track = await YT.track(query, video=False)
            if track:
                track.is_video = False
                return track
        return None

    # Saavn first for Indian songs (fast)
    track = await saavn.get_first_result(query)
    if track:
        return track

    # YouTube fallback
    track = await YT.track(query, video=video)
    if track:
        return track

    return None


# ═══════════════════════════════════════════════════
# AI SUGGESTIONS
# ═══════════════════════════════════════════════════
async def ai_suggest_songs(mood: str, count: int = 5) -> list[str]:
    try:
        url = f"{_AI_API_BASE}{mood}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            text = resp.text.strip()

        songs = [s.strip() for s in text.splitlines() if s.strip()]
        if len(songs) == 1:
            songs = [text[:50]]

        cleaned = []
        for s in songs[:count]:
            s = re.sub(r"^\d+\.\s*", "", s)
            s = s.strip().strip('"').strip("'")
            if s and len(s) > 2:
                cleaned.append(s)

        return cleaned if cleaned else _fallback_suggestions(count)
    except Exception as e:
        logger.debug(f"AI suggest error: {e}")
        return _fallback_suggestions(count)


def _fallback_suggestions(count: int) -> list[str]:
    trending = [
        "Tum Hi Ho", "Kesariya", "Raataan Lambiyan",
        "Believer Imagine Dragons", "Shape of You",
        "Channa Mereya", "Perfect Ed Sheeran",
        "Tere Vaaste", "Dilbar", "Senorita",
        "Apna Bana Le", "Stereo Hearts",
        "Kabira", "Love Me Like You Do",
        "Satranga", "Faded Alan Walker",
        "O Bedardeya", "Let Me Love You",
        "Phir Aur Kya Chahiye", "See You Again",
        "Pehle Bhi Main", "Stay Justin Bieber",
        "Lutt Putt Gaya", "Levitating Dua Lipa",
        "Ae Dil Hai Mushkil", "Memories Maroon 5",
    ]
    return random.sample(trending, min(count, len(trending)))


# ═══════════════════════════════════════════════════
# STREAM CORE (FIXED FX)
# ═══════════════════════════════════════════════════
async def start_stream(cid: int, track: Track, video: bool = False):
    state = queues.get(cid)
    dsp = state.dsp_mode

    # Build MediaStream with proper ffmpeg parameters
    if video or track.is_video:
        if dsp != "standard" and dsp in _DSP_FILTERS and _DSP_FILTERS[dsp]:
            ffmpeg_params = f"-af {_DSP_FILTERS[dsp]}"
            logger.info(f"🎛️ FX [{dsp}]: {ffmpeg_params}")
            stream = MediaStream(
                track.url,
                audio_parameters=_AUDIO_QUALITY,
                video_parameters=_VIDEO_QUALITY,
                ffmpeg_parameters=ffmpeg_params,
            )
        else:
            stream = MediaStream(
                track.url,
                audio_parameters=_AUDIO_QUALITY,
                video_parameters=_VIDEO_QUALITY,
            )
    else:
        if dsp != "standard" and dsp in _DSP_FILTERS and _DSP_FILTERS[dsp]:
            ffmpeg_params = f"-af {_DSP_FILTERS[dsp]}"
            logger.info(f"🎛️ FX [{dsp}]: {ffmpeg_params}")
            stream = MediaStream(
                track.url,
                audio_parameters=_AUDIO_QUALITY,
                video_flags=MediaStream.Flags.IGNORE,
                ffmpeg_parameters=ffmpeg_params,
            )
        else:
            stream = MediaStream(
                track.url,
                audio_parameters=_AUDIO_QUALITY,
                video_flags=MediaStream.Flags.IGNORE,
            )

    await calls.play(cid, stream)

    # Apply volume
    try:
        await calls.change_volume_call(cid, state.volume)
    except Exception:
        pass


async def send_card(cid: int, state: ChatState, video: bool = False):
    if not state.current:
        return

    item = state.current
    track = item.track
    dsp = state.dsp_mode
    dsp_label = _DSP_NAMES.get(dsp, dsp)
    dur = track.duration_str
    src = "🎬 Video" if (video or track.is_video) else "🎵 Saavn" if "Saavn" in (track.album or "") else "📺 YouTube"
    q = len(state.queue)
    status = "⏸️ Paused" if state.is_paused else "▶️ Playing"
    vol = state.volume

    # Premium UI
    caption = (
        f"━━━━━━━━━━━━━━━\n"
        f"🎶 <b>{track.title}</b>\n"
        f"👤 <i>{track.artist}</i>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{src}  |  ⏱ {dur}  |  {status}\n"
        f"🎛️ FX: {dsp_label}  |  🔊 {vol}%  |  📋 {q}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 <i>Requested by {item.requested_by}</i>\n"
        f"⚡ {OWNER_TAG}"
    )

    old = NOW_MSG.pop(cid, None)
    if old:
        try:
            await bot.delete_messages(cid, old)
        except Exception:
            pass

    try:
        msg = await bot.send_photo(
            cid,
            photo=track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=btns(state),
        )
        NOW_MSG[cid] = msg.id
    except Exception:
        try:
            msg = await bot.send_message(
                cid,
                caption,
                reply_markup=btns(state),
            )
            NOW_MSG[cid] = msg.id
        except Exception:
            pass


async def advance(cid: int):
    nxt = queues.next(cid)

    if not nxt:
        state = queues.get(cid)
        if state.ai_autoplay:
            asyncio.create_task(ai_autofill_and_play(cid))
            return

        try:
            await calls.leave_call(cid)
        except Exception:
            pass
        NOW_MSG.pop(cid, None)
        return

    try:
        is_video = nxt.track.is_video
        await start_stream(cid, nxt.track, is_video)
        await send_card(cid, queues.get(cid), is_video)
    except Exception as e:
        logger.warning(f"Advance error: {e}")
        queues.get(cid).loop = False
        await asyncio.sleep(0.5)
        await advance(cid)


async def ai_autofill_and_play(cid: int):
    try:
        suggestions = await ai_suggest_songs("random trending", count=2)
        added_any = False
        for song_query in suggestions:
            track = await find_track(song_query, video=False)
            if track:
                ok, pos = queues.add_sync(cid, track, "🤖 AutoPlay")
                added_any = True
                await asyncio.sleep(0.3)

        if added_any:
            nxt = queues.next(cid)
            if nxt:
                await start_stream(cid, nxt.track, False)
                await send_card(cid, queues.get(cid), False)
        else:
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            NOW_MSG.pop(cid, None)
    except Exception as e:
        logger.debug(f"AI autofill error: {e}")
        try:
            await calls.leave_call(cid)
        except Exception:
            pass


@calls.on_update()
async def on_end(_, update):
    cid = getattr(update, "chat_id", None)
    if type(update).__name__ in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and cid:
        await advance(cid)


# ═══════════════════════════════════════════════════
# UI BUTTONS
# ═══════════════════════════════════════════════════
def btns(state: ChatState) -> InlineKeyboardMarkup:
    pp = ("▶️ Resume", "q_resume") if state.is_paused else ("⏸️ Pause", "q_pause")
    lp = "🔁 Loop: ON" if state.loop else "🔁 Loop"
    ai = "🤖 AI: ON" if state.ai_autoplay else "🤖 AI: OFF"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp[0], callback_data=pp[1]),
            InlineKeyboardButton("⏭️ Skip", callback_data="q_skip"),
            InlineKeyboardButton("⏹️ Stop", callback_data="q_stop"),
        ],
        [
            InlineKeyboardButton(lp, callback_data="q_loop"),
            InlineKeyboardButton("🔀 Shuffle", callback_data="q_shuffle"),
            InlineKeyboardButton("🎛️ FX", callback_data="q_fx"),
        ],
        [
            InlineKeyboardButton("📋 Queue", callback_data="q_queue"),
            InlineKeyboardButton(ai, callback_data="q_autotoggle"),
            InlineKeyboardButton("🗑️ Clear", callback_data="q_remove"),
        ],
        [
            InlineKeyboardButton("🔊 Vol+", callback_data="q_vol_up"),
            InlineKeyboardButton("🔉 Vol-", callback_data="q_vol_down"),
            InlineKeyboardButton("📊 Stats", callback_data="q_stats"),
        ],
    ])


def fx_btns(state: ChatState) -> InlineKeyboardMarkup:
    current = state.dsp_mode
    effects = list(_DSP_NAMES.items())
    rows = []
    for i in range(0, len(effects), 3):
        row = []
        for key, label in effects[i:i+3]:
            prefix = "✅ " if key == current else ""
            row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"fx_{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="q_back")])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════
# PLAY HANDLER (FAST — no extra delays)
# ═══════════════════════════════════════════════════
async def _play(cid: int, query: str, by: str, msg: Message, video: bool = False):
    asyncio.create_task(auto_del(msg))
    status = await bot.send_message(cid, "🔍 <b>Searching...</b>")

    t0 = time.time()
    track = await find_track(query, video)
    elapsed = round(time.time() - t0, 1)

    if not track:
        await safe_edit(status, "❌ Not found. Try another song or URL.")
        await asyncio.sleep(3)
        await safe_del(status)
        return

    added, pos = queues.add(cid, track, by)
    if not added:
        await safe_edit(status, "📛 Queue full (max 50).")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    if pos == 0:
        try:
            await start_stream(cid, track, video)
            await safe_del(status)
            await send_card(cid, queues.get(cid), video)
        except NoActiveGroupCall:
            await safe_edit(status, "❌ Start a voice chat first!")
            await asyncio.sleep(4)
            await safe_del(status)
            queues.clear(cid)
        except Exception as e:
            logger.error(f"Play error: {e}")
            await safe_edit(status, f"❌ Error: {str(e)[:50]}")
            await asyncio.sleep(3)
            await safe_del(status)
    else:
        await safe_edit(status, f"✅ Added #{pos} | ⏱ {elapsed}s | {track.title[:30]}")
        await asyncio.sleep(2)
        await safe_del(status)


# ═══════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════
@bot.on_message(filters.command("start"))
async def cmd_start(_, msg: Message):
    await msg.reply_text(
        "╔═══════════════════════╗\n"
        "║  🎵 <b>IMAXL VC MUSIC</b>  ║\n"
        "╚═══════════════════════╝\n\n"
        "Add me to your group, start a voice chat,\n"
        "and play music with <code>/play song</code>\n\n"
        "<b>✨ Features:</b>\n"
        "• 🎬 4K Video + Studio Audio\n"
        "• 🤖 AI Smart Suggestions\n"
        "• 🎛️ 9 Real FX: Slowed, Reverb, 8D, LoFi\n"
        "• 📋 Auto Queue + Anti-Spam\n"
        "• ⚡ Ultra Fast Playback\n\n"
        f"⚡ {OWNER_TAG}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}"),
            InlineKeyboardButton("📖 Help", callback_data="q_help"),
        ]])
    )


@bot.on_message(filters.command("play") & filters.group)
async def cmd_play(_, msg: Message):
    if len(msg.command) < 2:
        r = await msg.reply_text("🎵 <code>/play song name or URL</code>")
        await asyncio.sleep(2)
        await safe_del(r)
        return
    query = " ".join(msg.command[1:])
    await _play(msg.chat.id, query, uname(msg), msg, video=False)


@bot.on_message(filters.command("vplay") & filters.group)
async def cmd_vplay(_, msg: Message):
    if len(msg.command) < 2:
        r = await msg.reply_text("🎬 <code>/vplay song name or URL</code>")
        await asyncio.sleep(2)
        await safe_del(r)
        return
    query = " ".join(msg.command[1:])
    await _play(msg.chat.id, query, uname(msg), msg, video=True)


@bot.on_message(filters.command("aiplay") & filters.group)
async def cmd_aiplay(_, msg: Message):
    if len(msg.command) < 2:
        r = await msg.reply_text("🤖 <code>/aiplay mood</code> — sad, party, romantic")
        await asyncio.sleep(2)
        await safe_del(r)
        return

    asyncio.create_task(auto_del(msg))
    mood = " ".join(msg.command[1:])
    cid = msg.chat.id
    status = await bot.send_message(cid, f"🤖 <b>AI finding '{mood}'...</b>")

    suggestions = await ai_suggest_songs(mood, count=5)
    if not suggestions:
        await safe_edit(status, "❌ AI failed. Try again.")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    await safe_edit(status, f"✅ Found {len(suggestions)} songs. Playing...")

    for song in suggestions:
        track = await find_track(song, video=False)
        if track:
            added, pos = queues.add(cid, track, f"{uname(msg)} (AI)")
            if added and pos == 0:
                try:
                    await start_stream(cid, track, False)
                    await safe_del(status)
                    await send_card(cid, queues.get(cid), False)
                    return
                except NoActiveGroupCall:
                    await safe_edit(status, "❌ Start VC first!")
                    await asyncio.sleep(3)
                    await safe_del(status)
                    queues.clear(cid)
                    return
            elif added:
                await safe_edit(status, f"✅ #{pos}: {track.title[:25]}")
                await asyncio.sleep(0.5)

    await safe_edit(status, "✅ AI Queue ready!")
    await asyncio.sleep(1)
    await safe_del(status)


@bot.on_message(filters.command("skip") & filters.group)
async def cmd_skip(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    if not state.is_playing:
        return
    state.loop = False
    await advance(msg.chat.id)


@bot.on_message(filters.command(["stop", "end", "leave"]) & filters.group)
async def cmd_stop(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    cid = msg.chat.id
    queues.clear(cid)
    try:
        await calls.leave_call(cid)
    except Exception:
        pass
    old = NOW_MSG.pop(cid, None)
    if old:
        try:
            await bot.delete_messages(cid, old)
        except Exception:
            pass


@bot.on_message(filters.command("pause") & filters.group)
async def cmd_pause(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    if not state.is_playing or state.is_paused:
        return
    await calls.pause_stream(msg.chat.id)
    state.is_paused = True
    await send_card(msg.chat.id, state)


@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    if not state.is_paused:
        return
    await calls.resume_stream(msg.chat.id)
    state.is_paused = False
    await send_card(msg.chat.id, state)


@bot.on_message(filters.command("loop") & filters.group)
async def cmd_loop(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    if not state.is_playing:
        return
    state.loop = not state.loop
    await send_card(msg.chat.id, state)


@bot.on_message(filters.command(["fx", "effect", "mode"]) & filters.group)
async def cmd_fx(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    r = await msg.reply_text("🎛️ <b>Select Audio Effect:</b>", reply_markup=fx_btns(state))
    await asyncio.sleep(20)
    await safe_del(r)


@bot.on_message(filters.command(["queue", "q"]) & filters.group)
async def cmd_queue(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)

    if not state.current and not state.queue:
        r = await msg.reply_text("📭 Queue is empty.")
        await asyncio.sleep(2)
        await safe_del(r)
        return

    lines = ["╔══════ 📋 QUEUE ══════╗"]
    if state.current:
        dsp = _DSP_NAMES.get(state.dsp_mode, "Standard")
        lines.append(f"▶️ NOW: {state.current.track.title[:35]}")
        lines.append(f"🎛️ FX: {dsp}")
    if state.queue:
        lines.append("╠══════ NEXT ══════╣")
        for i, item in enumerate(state.queue[:10], 1):
            lines.append(f"{i}. {item.track.title[:35]}")
        if len(state.queue) > 10:
            lines.append(f"+{len(state.queue) - 10} more")

    ai_status = "🟢 ON" if state.ai_autoplay else "🔴 OFF"
    lines.append(f"╚══════ 🤖 AI: {ai_status} ══════╝")
    lines.append(f"⚡ {OWNER_TAG}")

    r = await msg.reply_text("\n".join(lines))
    await asyncio.sleep(10)
    await safe_del(r)


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    queues.shuffle(msg.chat.id)
    r = await msg.reply_text("🔀 Shuffled!")
    await asyncio.sleep(1)
    await safe_del(r)


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_rm(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    if len(msg.command) < 2:
        return
    try:
        item = queues.remove_at(msg.chat.id, int(msg.command[1]))
        if item:
            r = await msg.reply_text(f"🗑️ Removed: {item.track.title[:30]}")
            await asyncio.sleep(1)
            await safe_del(r)
    except Exception:
        pass


@bot.on_message(filters.command(["np", "now"]) & filters.group)
async def cmd_np(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    if state.current:
        await send_card(msg.chat.id, state)


@bot.on_message(filters.command(["autoplay", "aiplaytoggle"]) & filters.group)
async def cmd_autoplay(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    new_state = queues.toggle_ai(msg.chat.id)
    status = "🟢 ON" if new_state else "🔴 OFF"
    r = await msg.reply_text(f"🤖 AI AutoPlay: {status}")
    await asyncio.sleep(2)
    await safe_del(r)


@bot.on_message(filters.command(["vol", "volume"]) & filters.group)
async def cmd_volume(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    if len(msg.command) < 2:
        r = await msg.reply_text("🔊 <code>/vol 1-200</code>")
        await asyncio.sleep(2)
        await safe_del(r)
        return
    try:
        vol = int(msg.command[1])
        vol = max(1, min(200, vol))
        state = queues.get(msg.chat.id)
        state.volume = vol
        await calls.change_volume_call(msg.chat.id, vol)
        r = await msg.reply_text(f"🔊 Volume: {vol}%")
        await asyncio.sleep(1)
        await safe_del(r)
    except Exception:
        pass


# ── Owner Commands ──────────────────────────────────
@bot.on_message(filters.command(["restart", "reload"]) & filters.group)
async def cmd_restart(_, msg: Message):
    if not is_sudo(msg):
        asyncio.create_task(auto_del(msg))
        return
    r = await msg.reply_text("🔄 Restarting...")
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable, __file__])


@bot.on_message(filters.command("ping") & filters.group)
async def cmd_ping(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    t1 = time.time()
    r = await msg.reply_text("🏓 ...")
    t2 = time.time()
    ms = round((t2 - t1) * 1000)
    await safe_edit(r, f"🏓 {ms}ms | ⚡ {OWNER_TAG}")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("cookies") & filters.group)
async def cmd_ck(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    found = "🟢 Yes" if COOKIES_PATH else "🔴 No"
    r = await msg.reply_text(f"🍪 Cookies: {found}")
    await asyncio.sleep(2)
    await safe_del(r)


@bot.on_message(filters.command("reloadcookies") & filters.group)
async def cmd_rcook(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    if not is_sudo(msg):
        return
    find_cookies()
    r = await msg.reply_text(f"🍪 Reloaded: {'Yes' if COOKIES_PATH else 'No'}")
    await asyncio.sleep(2)
    await safe_del(r)


@bot.on_message(filters.command("help") & filters.group)
async def cmd_help(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    r = await msg.reply_text(
        "╔══════ 🎵 IMAXL HELP ══════╗\n\n"
        "<b>🎵 Play</b>\n"
        "<code>/play song</code> — Audio\n"
        "<code>/vplay song/URL</code> — Video 4K\n"
        "<code>/aiplay mood</code> — AI pick\n\n"
        "<b>🎛️ Controls</b>\n"
        "<code>/pause /resume /skip /stop</code>\n"
        "<code>/loop /shuffle /fx</code>\n"
        "<code>/vol 1-200</code>\n\n"
        "<b>📋 Queue</b>\n"
        "<code>/queue /remove index /np</code>\n"
        "<code>/autoplay</code> — AI toggle\n\n"
        "╚═══════════════════════╝\n"
        f"⚡ {OWNER_TAG}",
    )
    await asyncio.sleep(20)
    await safe_del(r)


# ═══════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════
@bot.on_callback_query(filters.regex(r"^q_"))
async def cb(_, q: CallbackQuery):
    a = q.data
    cid = q.message.chat.id
    state = queues.get(cid)

    try:
        if a == "q_pause":
            if not state.is_playing or state.is_paused:
                return await q.answer("❌ Not playing")
            await calls.pause_stream(cid)
            state.is_paused = True
            await q.answer("⏸️ Paused")
            if state.current:
                await send_card(cid, state)

        elif a == "q_resume":
            if not state.is_paused:
                return await q.answer("❌ Not paused")
            await calls.resume_stream(cid)
            state.is_paused = False
            await q.answer("▶️ Resumed")
            if state.current:
                await send_card(cid, state)

        elif a == "q_skip":
            if not state.is_playing:
                return await q.answer("❌ Not playing")
            state.loop = False
            await q.answer("⏭️ Skipped")
            await advance(cid)

        elif a == "q_stop":
            queues.clear(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            await safe_del(q.message)
            NOW_MSG.pop(cid, None)
            await q.answer("⏹️ Stopped")

        elif a == "q_loop":
            if not state.is_playing:
                return await q.answer("❌ Not playing")
            state.loop = not state.loop
            await q.answer(f"🔁 Loop {'ON' if state.loop else 'OFF'}")
            if state.current:
                await send_card(cid, state)

        elif a == "q_shuffle":
            if not state.queue:
                return await q.answer("📭 Empty")
            queues.shuffle(cid)
            await q.answer("🔀 Shuffled")

        elif a == "q_fx":
            await q.message.edit_reply_markup(reply_markup=fx_btns(state))
            await q.answer("🎛️ Select FX")

        elif a == "q_back":
            await q.message.edit_reply_markup(reply_markup=btns(state))
            await q.answer("🔙 Back")

        elif a == "q_autotoggle":
            new_state = queues.toggle_ai(cid)
            await q.answer(f"🤖 AI {'ON' if new_state else 'OFF'}")
            if state.current:
                await send_card(cid, state)

        elif a == "q_queue":
            if not state.current and not state.queue:
                return await q.answer("📭 Empty")
            lines = []
            if state.current:
                lines.append(f"▶️ {state.current.track.title[:30]}")
            for i, item in enumerate(state.queue[:8], 1):
                lines.append(f"{i}. {item.track.title[:30]}")
            if len(state.queue) > 8:
                lines.append(f"+{len(state.queue) - 8}")
            await q.answer("\n".join(lines), show_alert=True)

        elif a == "q_remove":
            if not state.queue:
                return await q.answer("📭 Empty")
            item = queues.remove_at(cid, 1)
            await q.answer(f"🗑️ {item.track.title[:25]}" if item else "—", show_alert=True)

        elif a == "q_vol_up":
            new_vol = min(200, state.volume + 10)
            state.volume = new_vol
            try:
                await calls.change_volume_call(cid, new_vol)
            except Exception:
                pass
            await q.answer(f"🔊 {new_vol}%")
            if state.current:
                await send_card(cid, state)

        elif a == "q_vol_down":
            new_vol = max(1, state.volume - 10)
            state.volume = new_vol
            try:
                await calls.change_volume_call(cid, new_vol)
            except Exception:
                pass
            await q.answer(f"🔉 {new_vol}%")
            if state.current:
                await send_card(cid, state)

        elif a == "q_stats":
            total = sum(1 for s in queues._chats.values() if s.is_playing)
            queued = sum(len(s.queue) for s in queues._chats.values())
            await q.answer(f"🎵 Active: {total}\n📋 Queued: {queued}", show_alert=True)

        elif a == "q_help":
            await q.answer(
                "/play song | /vplay URL | /aiplay mood\n"
                "/pause /resume /skip /stop /loop\n"
                "/shuffle /fx /vol 1-200 /queue\n"
                "/autoplay /remove index /np",
                show_alert=True,
            )

    except Exception as e:
        logger.exception(f"CB {a}: {e}")


@bot.on_callback_query(filters.regex(r"^fx_"))
async def fx_cb(_, q: CallbackQuery):
    mode = q.data.replace("fx_", "")
    cid = q.message.chat.id
    state = queues.get(cid)

    if mode not in _DSP_FILTERS:
        return await q.answer("❌ Invalid FX")

    queues.set_dsp(cid, mode)
    await q.answer(f"🎛️ {_DSP_NAMES.get(mode, mode)}")

    # Restart stream with new FX
    if state.is_playing and state.current:
        try:
            track = state.current.track
            is_video = track.is_video
            await start_stream(cid, track, is_video)
            await send_card(cid, state, is_video)
        except Exception as e:
            logger.warning(f"FX restart: {e}")

    await q.message.edit_reply_markup(reply_markup=fx_btns(state))


# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════
async def main():
    logger.info("🚀 Starting IMAXL VC Music Bot v4.1...")
    await bot.start()
    logger.info("🤖 Bot ready")
    await assistant.start()
    logger.info("👤 Assistant ready")
    await calls.start()
    logger.info("📞 Calls ready")
    logger.info(f"✅ Owner: {OWNER_USERNAME}")
    await idle()


if __name__ == "__main__":
    bot.loop.run_until_complete(main())
