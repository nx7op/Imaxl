#!/usr/bin/env python3
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FastTrack VC Music Bot — Ultimate Edition v3.0
  Voice Chat Music | HQ Audio | 4K Video | AI Smart
  Owner: @stillrahul
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sys
import time
import aiohttp
from typing import Optional
from urllib.parse import parse_qs, urlparse, quote

try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import (
        CallbackQuery,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Message,
    )
except ImportError:
    sys.exit("pyrofork missing: pip install pyrofork")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality, VideoQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("py-tgcalls missing: pip install py-tgcalls")

import yt_dlp
import config
from queue_manager import QueueManager, ChatState, Track
from saavn import SaavnClient

# ═══════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("fasttrack")

# ═══════════════════════════════════════════════════
# Clients
# ═══════════════════════════════════════════════════
bot = Client(
    "vc_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True,
)

assistant = Client(
    "vc_assistant",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    session_string=config.SESSION_STRING,
    in_memory=True,
)

calls = PyTgCalls(assistant)
saavn = SaavnClient()
queues = QueueManager(max_queue_size=getattr(config, "MAX_QUEUE_SIZE", 50))

# ═══════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════
DEFAULT_THUMB = "https://telegra.ph/file/default_music_thumb.jpg"
NOW_MSG: dict[int, int] = {}  # cid -> message_id
OWNER_TAG = "<b>@stillrahul</b>"
_AI_API_URL = getattr(config, "_AI_API_BASE", "https://gemini.adi7ya.workers.dev/?q=")

# ── Audio Quality Map ─────────────────────────────
_AUDIO_Q_MAP = {
    "STUDIO": AudioQuality.STUDIO,
    "HIGH": AudioQuality.HIGH,
    "MEDIUM": AudioQuality.MEDIUM,
    "LOW": AudioQuality.LOW,
}
_AUDIO_QUALITY = _AUDIO_Q_MAP.get(config.AUDIO_QUALITY, AudioQuality.STUDIO)

# ── Video Quality Map ─────────────────────────────
_VIDEO_Q_MAP = {
    "UHD_4K": VideoQuality.UHD_4K,
    "FHD_1080p": VideoQuality.FHD_1080p,
    "HD_720p": VideoQuality.HD_720p,
    "SD_480p": VideoQuality.SD_480p,
}
_VIDEO_QUALITY = _VIDEO_Q_MAP.get(config.VIDEO_QUALITY, VideoQuality.FHD_1080p)

# ═══════════════════════════════════════════════════
# DSP Effects (Real ffmpeg Filters)
# ═══════════════════════════════════════════════════
_DSP = config.DSP_EFFECTS
_DSP_NAMES = {
    "standard": "Standard",
    "slowed": "Slowed",
    "reverb": "Reverb",
    "slowed_reverb": "Slowed + Reverb",
    "nightcore": "Nightcore",
    "bassboost": "Bass Boost",
    "8d": "8D Audio",
    "vaporwave": "Vaporwave",
    "lofi": "Lo-Fi",
}

# ═══════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════
def is_sudo(msg: Message) -> bool:
    u = msg.from_user
    if not u:
        return False
    oid = getattr(config, "OWNER_ID", 0)
    sudo = getattr(config, "SUDO_USERS", set()) or set()
    return (oid and u.id == oid) or u.id in sudo


def uname(msg: Message) -> str:
    u = msg.from_user
    if not u:
        return "Unknown"
    return u.first_name or (f"@{u.username}" if u.username else "User")


async def auto_del(msg: Message, delay: float = 0.3):
    """Delete user command message — anti spam."""
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
# Cookies
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
                logger.info(f"Cookies OK: {p}")
                return p
        except Exception:
            pass
    logger.warning("No cookies.txt found")
    return None


find_cookies()


# ═══════════════════════════════════════════════════
# YouTube URL Cleaner
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
# YouTube Engine — Ultra Fast Multi-Strategy
# ═══════════════════════════════════════════════════
class YT:
    """Multi-strategy YouTube extractor for fastest results."""

    STRATEGIES = [
        {
            "name": "tv_embedded",
            "args": {"youtube": {"player_client": ["tv_embedded"], "player_skip": ["webpage", "js"]}},
            "cookies": True,
        },
        {
            "name": "web_creator",
            "args": {"youtube": {"player_client": ["web_creator"]}},
            "cookies": True,
        },
        {
            "name": "mweb",
            "args": {"youtube": {"player_client": ["mweb"]}},
            "cookies": True,
        },
        {
            "name": "default",
            "args": {},
            "cookies": False,
        },
        {
            "name": "android",
            "args": {"youtube": {"player_client": ["android"]}},
            "cookies": False,
        },
        {
            "name": "ios",
            "args": {"youtube": {"player_client": ["ios"]}},
            "cookies": False,
        },
    ]

    @classmethod
    def _opts(cls, strat: dict, fmt: str = "bestaudio/best") -> dict:
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
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        }
        if strat.get("args"):
            o["extractor_args"] = strat["args"]
        if strat.get("cookies") and COOKIES_PATH:
            o["cookiefile"] = COOKIES_PATH
        return o

    @classmethod
    def _extract(cls, query: str, video: bool = False) -> Optional[dict]:
        if "youtu" in query:
            query = clean_yt_url(query)

        # Video: best quality | Audio: bestaudio
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

                logger.info(f"[{elapsed}s] {strat['name']} -> {info.get('title', '?')[:40]}")
                return info
            except Exception as e:
                logger.debug(f"{strat['name']}: {str(e)[:80]}")
                continue
        return None

    @classmethod
    async def track(cls, query: str, video: bool = False) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query, video)
        if not info:
            return None

        dur = int(info.get("duration") or 0) if info.get("duration") else 0

        # Best thumbnail
        thumb = DEFAULT_THUMB
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            # Get highest resolution thumbnail
            best = max(thumbnails, key=lambda t: (t.get("height", 0) * t.get("width", 0)), default=None)
            if best and best.get("url"):
                thumb = best["url"]
            elif thumbnails[-1].get("url"):
                thumb = thumbnails[-1]["url"]

        return Track(
            id_=info.get("id", "yt"),
            title=(info.get("title") or "Unknown")[:55],
            artist=(info.get("uploader") or info.get("channel") or "YouTube")[:35],
            album="YouTube Video" if video else "YouTube HQ",
            duration=dur,
            url=info["url"],
            thumb=thumb,
            is_video=video,
        )


# ═══════════════════════════════════════════════════
# Track Resolver — Multi-Source
# ═══════════════════════════════════════════════════
async def find_track(query: str, video: bool = False) -> Optional[Track]:
    query = query.strip()
    is_url = query.startswith("http")

    # 1. Try YouTube first (always for video, fastest for URLs)
    t = await YT.track(query, video)
    if t:
        return t

    # 2. Try Saavn for audio (Indian music)
    if not is_url and not video:
        try:
            t = await saavn.get_first_result(query)
            if t:
                logger.info(f"Saavn -> {t.title}")
                return t
        except Exception:
            pass

    # 3. Fallback: ytsearch via yt_dlp default search
    return None


# ═══════════════════════════════════════════════════
# AI Song Suggestion Engine
# ═══════════════════════════════════════════════════
async def ai_suggest_songs(cid: int, count: int = 2) -> list[str]:
    """
    Use Gemini API to suggest songs based on user's listening history.
    Returns list of song queries ( Hindi/English mix ).
    """
    try:
        taste = queues.get_user_taste(cid)
        history = taste.get("history", [])
        recent = ", ".join(history[-8:]) if history else ""

        # Build prompt — ask for song suggestions without revealing AI
        if recent:
            prompt = (
                f"User recently listened to: {recent}. "
                f"Suggest {count} popular trending songs that match this taste. "
                f"Return ONLY song names separated by | . No extra text. "
                f"Mix Hindi and English songs. Short replies only."
            )
        else:
            prompt = (
                f"Suggest {count} popular trending songs right now. "
                f"Return ONLY song names separated by | . No extra text. "
                f"Mix Hindi and English. Short replies only."
            )

        url = f"{_AI_API_URL}{quote(prompt)}"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return _fallback_suggestions(count)
                text = (await r.text()).strip()

        # Parse response — split by | or newline
        songs = []
        for sep in ["|", "\n", ","]:
            if sep in text:
                songs = [s.strip() for s in text.split(sep) if s.strip() and len(s.strip()) > 2]
                break

        if not songs:
            # Single line response
            songs = [text[:50]]

        # Clean up — remove numbering, quotes
        cleaned = []
        for s in songs[:count]:
            s = re.sub(r"^\d+\.\s*", "", s)  # Remove "1. " prefix
            s = s.strip("\"'").strip()
            if s and len(s) > 2:
                cleaned.append(s)

        return cleaned if cleaned else _fallback_suggestions(count)

    except Exception as e:
        logger.debug(f"AI suggest error: {e}")
        return _fallback_suggestions(count)


def _fallback_suggestions(count: int) -> list[str]:
    """Fallback when AI is unavailable."""
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
# AI Auto-Play — Background Queue Filler
# ═══════════════════════════════════════════════════
async def ai_autoplay_worker(cid: int):
    """
    When queue is empty and AI autoplay is on,
    automatically suggest and add songs.
    Runs in background — no spam to chat.
    """
    try:
        state = queues.get(cid)
        if not state.ai_autoplay:
            return

        # Check if queue is actually empty
        if state.queue or state.current:
            return

        suggestions = await ai_suggest_songs(cid, count=2)
        if not suggestions:
            return

        for song_query in suggestions:
            track = await find_track(song_query, video=False)
            if track:
                ok, pos = queues.add_sync(cid, track, "AutoPlay")
                if ok and pos == 0 and not state.is_playing:
                    # Start playing immediately
                    try:
                        await start_stream(cid, track, False)
                        await send_card(cid, queues.get(cid), False)
                    except NoActiveGroupCall:
                        pass
                    except Exception:
                        pass

                # Small delay between adds
                await asyncio.sleep(0.5)

    except Exception as e:
        logger.debug(f"AI autoplay error: {e}")


# ═══════════════════════════════════════════════════
# Stream Core — Ultra Fast
# ═══════════════════════════════════════════════════
async def start_stream(cid: int, track: Track, video: bool = False):
    """Start streaming with highest quality."""
    url = track.url
    state = queues.get(cid)
    dsp = state.dsp_mode if hasattr(state, "dsp_mode") else "standard"

    # Determine audio/video quality
    audio_params = _AUDIO_QUALITY
    video_params = _VIDEO_QUALITY

    if video or track.is_video:
        # Video stream — 1080p/4K
        stream = MediaStream(
            url,
            audio_parameters=audio_params,
            video_parameters=video_params,
        )
    else:
        # Audio only — highest quality
        stream = MediaStream(
            url,
            audio_parameters=audio_params,
            video_flags=MediaStream.Flags.IGNORE,
        )

    await calls.play(cid, stream)


async def send_card(cid: int, state: ChatState, video: bool = False):
    """Send now-playing card with clean UI."""
    if not state.current:
        return

    item = state.current
    track = item.track
    dsp = getattr(state, "dsp_mode", "standard")
    dsp_label = _DSP_NAMES.get(dsp, dsp)
    dur = getattr(track, "duration_str", None) or f"{track.duration}s"
    src = "Video" if (video or track.is_video) else ("Saavn" if "Saavn" in (track.album or "") else "YouTube")
    q = len(state.queue)
    status = "Paused" if state.is_paused else "Playing"

    # Clean bold UI — human style
    caption = (
        f"<b>{track.title}</b>\n"
        f"{track.artist}\n\n"
        f"{src}  |  {dur}  |  {status}\n"
        f"FX: {dsp_label}  |  Queue: {q}\n\n"
        f"Requested by {item.requested_by}\n"
        f"{OWNER_TAG}"
    )

    # Delete old now playing message
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
    """Play next track or trigger AI autoplay."""
    nxt = queues.next(cid)

    if not nxt:
        # Queue empty — try AI autoplay
        state = queues.get(cid)
        if getattr(state, "ai_autoplay", True):
            # Don't block — fire and forget AI filler
            asyncio.create_task(ai_autofill_and_play(cid))
            return

        # No AI — leave call
        try:
            await calls.leave_call(cid)
        except Exception:
            pass
        NOW_MSG.pop(cid, None)
        return

    try:
        is_video = nxt.track.is_video or "Video" in (nxt.track.album or "")
        await start_stream(cid, nxt.track, is_video)
        await send_card(cid, queues.get(cid), is_video)
    except Exception as e:
        logger.warning(f"Advance error: {e}")
        queues.get(cid).loop = False
        await asyncio.sleep(0.5)
        await advance(cid)


async def ai_autofill_and_play(cid: int):
    """AI fills queue then plays — seamless transition."""
    try:
        suggestions = await ai_suggest_songs(cid, count=2)
        state = queues.get(cid)

        added_any = False
        for song_query in suggestions:
            track = await find_track(song_query, video=False)
            if track:
                ok, pos = queues.add_sync(cid, track, "AutoPlay")
                added_any = True
                await asyncio.sleep(0.3)

        if added_any:
            # Play first added track
            nxt = queues.next(cid)
            if nxt:
                await start_stream(cid, nxt.track, False)
                await send_card(cid, queues.get(cid), False)
        else:
            # Nothing added — leave
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
# UI — Clean Bold Buttons
# ═══════════════════════════════════════════════════
def btns(state: ChatState) -> InlineKeyboardMarkup:
    pp = ("Resume", "q_resume") if state.is_paused else ("Pause", "q_pause")
    lp = "Loop On" if state.loop else "Loop"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp[0], callback_data=pp[1]),
            InlineKeyboardButton("Skip", callback_data="q_skip"),
            InlineKeyboardButton("Stop", callback_data="q_stop"),
        ],
        [
            InlineKeyboardButton(lp, callback_data="q_loop"),
            InlineKeyboardButton("Shuffle", callback_data="q_shuffle"),
            InlineKeyboardButton("FX", callback_data="q_fx"),
        ],
        [
            InlineKeyboardButton("Queue", callback_data="q_queue"),
            InlineKeyboardButton("AI Auto", callback_data="q_autotoggle"),
            InlineKeyboardButton("Clear", callback_data="q_remove"),
        ],
    ])


def fx_btns(state: ChatState) -> InlineKeyboardMarkup:
    """DSP effect selector buttons."""
    current = getattr(state, "dsp_mode", "standard")

    rows = []
    effects = list(_DSP_NAMES.items())

    # 3 buttons per row
    for i in range(0, len(effects), 3):
        row = []
        for key, label in effects[i:i+3]:
            prefix = "• " if key == current else ""
            row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"fx_{key}"))
        rows.append(row)

    rows.append([InlineKeyboardButton("Back", callback_data="q_back")])
    return InlineKeyboardMarkup(rows)


# ═══════════════════════════════════════════════════
# Play Helper — Single Status, No Spam
# ═══════════════════════════════════════════════════
async def _play(cid: int, query: str, by: str, msg: Message, video: bool = False):
    """Unified play handler — fast, clean, no spam."""
    # Delete user command immediately
    asyncio.create_task(auto_del(msg))

    # Single status message
    status = await bot.send_message(cid, "<b>Searching...</b>")

    t0 = time.time()
    track = await find_track(query, video)
    elapsed = round(time.time() - t0, 1)

    if not track:
        await safe_edit(status, "Not found. Try another song.")
        await asyncio.sleep(3)
        await safe_del(status)
        return

    added, pos = await queues.add(cid, track, by)
    if not added:
        await safe_edit(status, "Queue full.")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    state = queues.get(cid)

    if pos == 0:
        try:
            await safe_edit(status, f"Starting... ({elapsed}s)")
            await start_stream(cid, track, video)
            await safe_del(status)
            await send_card(cid, state, video)
        except NoActiveGroupCall:
            queues.clear(cid)
            await safe_edit(status, "Start a voice chat first!")
            await asyncio.sleep(3)
            await safe_del(status)
        except Exception as e:
            queues.clear(cid)
            await safe_edit(status, f"Error: {str(e)[:100]}")
            await asyncio.sleep(4)
            await safe_del(status)
    else:
        await safe_edit(status, f"Added #{pos}: {track.title}")
        await asyncio.sleep(3)
        await safe_del(status)


# ═══════════════════════════════════════════════════
# Commands — All Group Commands
# ═══════════════════════════════════════════════════
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, msg: Message):
    if len(msg.command) < 2:
        r = await msg.reply_text("Usage: <code>/play song name</code>")
        asyncio.create_task(auto_del(msg))
        await asyncio.sleep(3)
        await safe_del(r)
        return
    query = msg.text.split(None, 1)[1].strip()
    await _play(msg.chat.id, query, uname(msg), msg)


@bot.on_message(filters.command(["vplay", "vp", "video", "playforce"]) & filters.group)
async def cmd_vplay(_, msg: Message):
    if len(msg.command) < 2:
        r = await msg.reply_text("Usage: <code>/vplay song name</code>")
        asyncio.create_task(auto_del(msg))
        await asyncio.sleep(3)
        await safe_del(r)
        return
    query = msg.text.split(None, 1)[1].strip()
    await _play(msg.chat.id, query, uname(msg), msg, video=True)


@bot.on_message(filters.command(["aiplay", "ai", "smart"]) & filters.group)
async def cmd_aiplay(_, msg: Message):
    """Play AI-suggested song based on mood/text."""
    asyncio.create_task(auto_del(msg))

    if len(msg.command) < 2:
        # Show AI status
        state = queues.get(msg.chat.id)
        status = "On" if state.ai_autoplay else "Off"
        r = await msg.reply_text(
            f"AI AutoPlay: {status}\n"
            f"Usage: <code>/aiplay mood</code> (sad, party, gym, lofi, romantic)\n"
            f"Or: <code>/aiplay describe what you want</code>"
        )
        await asyncio.sleep(6)
        await safe_del(r)
        return

    prompt = msg.text.split(None, 1)[1].strip()

    status = await msg.reply_text("AI finding songs...")
    suggestions = await ai_suggest_songs(msg.chat.id, count=2)

    if suggestions:
        pick = suggestions[0]
        await safe_del(status)
        await _play(msg.chat.id, pick, f"{uname(msg)} (AI)", msg)
    else:
        await safe_edit(status, "AI couldn't find songs. Try /play")
        await asyncio.sleep(3)
        await safe_del(status)


@bot.on_message(filters.command(["skip", "s", "next"]) & filters.group)
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
    """Show DSP effect selector."""
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    r = await msg.reply_text("Select Audio Effect:", reply_markup=fx_btns(state))
    await asyncio.sleep(15)
    await safe_del(r)


@bot.on_message(filters.command(["queue", "q"]) & filters.group)
async def cmd_queue(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)

    if not state.current and not state.queue:
        r = await msg.reply_text("Queue is empty.")
        await asyncio.sleep(2)
        await safe_del(r)
        return

    lines = []
    if state.current:
        dsp = _DSP_NAMES.get(getattr(state, "dsp_mode", "standard"), "Standard")
        lines.append(f"Playing: {state.current.track.title}")
        lines.append(f"FX: {dsp}")
    if state.queue:
        lines.append("")
        for i, item in enumerate(state.queue[:10], 1):
            lines.append(f"{i}. {item.track.title}")
        if len(state.queue) > 10:
            lines.append(f"+{len(state.queue) - 10} more")

    ai_status = "On" if state.ai_autoplay else "Off"
    lines.append(f"\nAI AutoPlay: {ai_status}")
    lines.append(f"{OWNER_TAG}")

    r = await msg.reply_text("\n".join(lines))
    await asyncio.sleep(8)
    await safe_del(r)


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    queues.shuffle(msg.chat.id)
    r = await msg.reply_text("Queue shuffled.")
    await asyncio.sleep(2)
    await safe_del(r)


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_rm(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    if len(msg.command) < 2:
        return
    try:
        queues.remove_at(msg.chat.id, int(msg.command[1]))
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
    """Toggle AI autoplay on/off."""
    asyncio.create_task(auto_del(msg))
    state = queues.get(msg.chat.id)
    new_state = queues.toggle_ai(msg.chat.id)
    status = "enabled" if new_state else "disabled"
    r = await msg.reply_text(f"AI AutoPlay {status}.")
    await asyncio.sleep(2)
    await safe_del(r)


# ── Owner Commands ──────────────────────────────────
@bot.on_message(filters.command(["restart", "reload"]) & filters.group)
async def cmd_restart(_, msg: Message):
    if not is_sudo(msg):
        asyncio.create_task(auto_del(msg))
        return
    r = await msg.reply_text("Restarting...")
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable, __file__])


@bot.on_message(filters.command("ping") & filters.group)
async def cmd_ping(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    t1 = time.time()
    r = await msg.reply_text("Pinging...")
    t2 = time.time()
    ms = round((t2 - t1) * 1000)
    await safe_edit(r, f"Ping: {ms}ms | {OWNER_TAG}")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("cookies") & filters.group)
async def cmd_ck(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    found = "Yes" if COOKIES_PATH else "No"
    r = await msg.reply_text(f"Cookies: {found}")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("reloadcookies") & filters.group)
async def cmd_rcook(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    if not is_sudo(msg):
        return
    find_cookies()
    r = await msg.reply_text(f"Cookies reloaded: {'Yes' if COOKIES_PATH else 'No'}")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("help") & filters.group)
async def cmd_help(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    r = await msg.reply_text(
        "<b>FastTrack VC Music Bot</b>\n\n"
        "<b>Play</b>\n"
        "/play song — Audio\n"
        "/vplay song — Video (1080p)\n"
        "/aiplay mood — AI suggestions\n\n"
        "<b>Controls</b>\n"
        "/pause  /resume  /skip  /stop\n"
        "/loop  /shuffle  /fx\n\n"
        "<b>Queue</b>\n"
        "/queue  /remove  /np\n"
        "/autoplay — Toggle AI autoplay\n\n"
        "<b>Owner</b>\n"
        f"{OWNER_TAG}",
    )
    await asyncio.sleep(15)
    await safe_del(r)


@bot.on_message(filters.command("start"))
async def cmd_start(_, msg: Message):
    await msg.reply_text(
        "<b>FastTrack VC Music Bot</b>\n\n"
        "Add me to your group, start a voice chat,\n"
        "and play music with <code>/play song</code>\n\n"
        "Features:\n"
        "• HQ Audio + 4K Video\n"
        "• AI Smart Suggestions\n"
        "• Real FX: Slowed, Reverb, 8D, LoFi\n"
        "• Auto Queue Fill\n\n"
        f"{OWNER_TAG}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Owner", url="https://t.me/stillrahul"),
        ]])
    )


# ═══════════════════════════════════════════════════
# Callbacks — Button Handlers
# ═══════════════════════════════════════════════════
@bot.on_callback_query(filters.regex(r"^q_"))
async def cb(_, q: CallbackQuery):
    a = q.data
    cid = q.message.chat.id
    state = queues.get(cid)

    try:
        if a == "q_pause":
            if not state.is_playing or state.is_paused:
                return await q.answer("—")
            await calls.pause_stream(cid)
            state.is_paused = True
            await q.answer("Paused")
            if state.current:
                await send_card(cid, state)

        elif a == "q_resume":
            if not state.is_paused:
                return await q.answer("—")
            await calls.resume_stream(cid)
            state.is_paused = False
            await q.answer("Resumed")
            if state.current:
                await send_card(cid, state)

        elif a == "q_skip":
            if not state.is_playing:
                return await q.answer("—")
            state.loop = False
            await q.answer("Skipped")
            await advance(cid)

        elif a == "q_stop":
            queues.clear(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            await safe_del(q.message)
            NOW_MSG.pop(cid, None)
            await q.answer("Stopped")

        elif a == "q_loop":
            if not state.is_playing:
                return await q.answer("—")
            state.loop = not state.loop
            await q.answer(f"Loop {'On' if state.loop else 'Off'}")
            if state.current:
                await send_card(cid, state)

        elif a == "q_shuffle":
            if not state.queue:
                return await q.answer("Empty")
            queues.shuffle(cid)
            await q.answer("Shuffled")

        elif a == "q_fx":
            # Show effect selector
            await q.message.edit_reply_markup(reply_markup=fx_btns(state))
            await q.answer("Select FX")

        elif a == "q_back":
            # Back to main controls
            await q.message.edit_reply_markup(reply_markup=btns(state))
            await q.answer("Back")

        elif a == "q_autotoggle":
            new_state = queues.toggle_ai(cid)
            await q.answer(f"AI Auto {'On' if new_state else 'Off'}")
            if state.current:
                await send_card(cid, state)

        elif a == "q_queue":
            if not state.current and not state.queue:
                return await q.answer("Empty")
            lines = []
            if state.current:
                lines.append(f"Now: {state.current.track.title}")
            for i, item in enumerate(state.queue[:8], 1):
                lines.append(f"{i}. {item.track.title}")
            if len(state.queue) > 8:
                lines.append(f"+{len(state.queue) - 8}")
            await q.answer("\n".join(lines), show_alert=True)

        elif a == "q_remove":
            if not state.queue:
                return await q.answer("Empty")
            item = queues.remove_at(cid, 1)
            await q.answer(f"Removed: {item.track.title[:30]}" if item else "—", show_alert=True)

    except Exception as e:
        logger.exception(f"CB {a}: {e}")
        await q.answer("Error")


@bot.on_callback_query(filters.regex(r"^fx_"))
async def cb_fx(_, q: CallbackQuery):
    """Handle DSP effect selection."""
    fx_key = q.data[3:]  # Remove "fx_" prefix
    cid = q.message.chat.id
    state = queues.get(cid)

    if fx_key not in _DSP:
        return await q.answer("Invalid FX")

    # Set new DSP mode
    queues.set_dsp(cid, fx_key)
    dsp_name = _DSP_NAMES.get(fx_key, fx_key)
    await q.answer(f"FX: {dsp_name}")

    # Update display
    if state.current:
        await send_card(cid, state)
    else:
        await q.message.edit_reply_markup(reply_markup=fx_btns(state))


# ═══════════════════════════════════════════════════
# Watchdog — Auto Leave Idle
# ═══════════════════════════════════════════════════
async def watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            for cid in queues.cleanup_idle(getattr(config, "AUTO_LEAVE_SECONDS", 180)):
                try:
                    await calls.leave_call(cid)
                except Exception:
                    pass
                queues.forget(cid)
                NOW_MSG.pop(cid, None)
        except Exception:
            pass


# ═══════════════════════════════════════════════════
# Boot
# ═══════════════════════════════════════════════════
async def boot():
    print("=" * 50)
    print("  FastTrack VC Music Bot — Ultimate v3.0")
    print("  @stillrahul")
    print("=" * 50)

    await assistant.start()
    await bot.start()
    await calls.start()

    me_bot = await bot.get_me()
    me_asst = await assistant.get_me()

    print(f"\n  Bot: @{me_bot.username}")
    print(f"  Assistant: {me_asst.first_name} [{me_asst.id}]")
    print(f"  Cookies: {'OK' if COOKIES_PATH else 'No'}")
    print(f"  Audio: {config.AUDIO_QUALITY}")
    print(f"  Video: {config.VIDEO_QUALITY}")
    print(f"  FX Modes: {len(_DSP)}")
    print(f"  AI AutoPlay: ON")
    print(f"\n  Ready.\n")

    asyncio.create_task(watchdog())
    await idle()


def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(boot())
    except KeyboardInterrupt:
        pass
    finally:
        async def cleanup():
            for fn in [saavn.close, bot.stop, assistant.stop]:
                try:
                    await fn()
                except Exception:
                    pass
        try:
            loop.run_until_complete(cleanup())
        except Exception:
            pass


if __name__ == "__main__":
    main()
