#!/usr/bin/env python3
"""
FastTrack VC Music Bot — Ultimate Edition
YouTube HQ Audio + Video Stream
Real LoFi Effect • Ultra Fast • Clean UI • AI Autoplay
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sys
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import (
        CallbackQuery,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Message,
    )
except ImportError:
    sys.exit("pyrofork missing")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality, VideoQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("py-tgcalls missing")

import yt_dlp
import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, ChatState
import ai_suggest

# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(config, "LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("fasttrack")

# ==============================================================================
# Clients
# ==============================================================================
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

DEFAULT_THUMB = "https://telegra.ph/file/default_music_thumb.jpg"
LOFI_CHATS: set[int] = set()
NOW_MSG: dict[int, int] = {}
AUTOPLAY_LOCK: dict[int, bool] = {}  # prevent double-trigger race

# ==============================================================================
# Helpers
# ==============================================================================
def is_sudo(msg: Message) -> bool:
    u = msg.from_user
    if not u:
        return False
    oid = getattr(config, "OWNER_ID", 0)
    sudo = getattr(config, "SUDO_USERS", set())
    return (oid and u.id == oid) or u.id in sudo


def uname(msg: Message) -> str:
    u = msg.from_user
    if not u:
        return "Unknown"
    return u.first_name or (f"@{u.username}" if u.username else "User")


async def auto_del(msg: Message, delay: float = 0.4):
    """Delete the user's own command message shortly after (keeps chat clean)."""
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


async def safe_edit(msg, text: str, markup=None):
    try:
        await msg.edit_text(text, reply_markup=markup)
    except Exception:
        pass


async def safe_del(msg):
    try:
        await msg.delete()
    except Exception:
        pass


async def flash(cid: int, text: str, seconds: float = 2.5):
    """Send a short-lived status message and clean it up — no spam left behind."""
    try:
        m = await bot.send_message(cid, text)
    except Exception:
        return
    await asyncio.sleep(seconds)
    await safe_del(m)


# ==============================================================================
# Cookies
# ==============================================================================
COOKIES_PATH: Optional[str] = None


def find_cookies() -> Optional[str]:
    global COOKIES_PATH
    for p in ["cookies.txt", "/app/cookies.txt",
              os.path.join(os.path.dirname(__file__), "cookies.txt")]:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 50:
                COOKIES_PATH = p
                logger.info(f"✅ Cookies: {p}")
                return p
        except Exception:
            pass
    logger.warning("⚠️ No cookies.txt")
    return None


find_cookies()


# ==============================================================================
# YouTube URL Cleaner
# ==============================================================================
def clean_yt_url(url: str) -> str:
    try:
        parsed = urlparse(url)
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


# ==============================================================================
# YouTube Engine — fastest strategy first, short timeouts, parallel-ready
# ==============================================================================
class YT:
    STRATEGIES = [
        {"name": "tv_embedded", "args": {"youtube": {"player_client": ["tv_embedded"], "player_skip": ["webpage", "js"]}}, "cookies": True},
        {"name": "web_creator", "args": {"youtube": {"player_client": ["web_creator"]}}, "cookies": True},
        {"name": "mweb", "args": {"youtube": {"player_client": ["mweb"]}}, "cookies": True},
        {"name": "default", "args": {}, "cookies": False},
        {"name": "android", "args": {"youtube": {"player_client": ["android"]}}, "cookies": False},
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
            "socket_timeout": 15,
            "retries": 2,
            "cachedir": False,
            "source_address": "0.0.0.0",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        if strat["args"]:
            o["extractor_args"] = strat["args"]
        if strat["cookies"] and COOKIES_PATH:
            o["cookiefile"] = COOKIES_PATH
        return o

    @classmethod
    def _extract(cls, query: str, video: bool = False) -> Optional[dict]:
        if "youtu" in query:
            query = clean_yt_url(query)

        fmt = "best" if video else "bestaudio/best"

        for strat in cls.STRATEGIES:
            try:
                with yt_dlp.YoutubeDL(cls._opts(strat, fmt)) as ydl:
                    info = ydl.extract_info(query, download=False)
                if not info:
                    continue
                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        continue
                    info = entries[0]
                if not info.get("url"):
                    continue
                logger.info(f"✅ {strat['name']} → {info.get('title', '?')[:35]}")
                return info
            except Exception as e:
                logger.warning(f"✗ {strat['name']}: {str(e)[:80]}")
                continue
        return None

    @classmethod
    async def track(cls, query: str, video: bool = False) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query, video)
        if not info:
            return None

        dur = int(info.get("duration") or 0) if info.get("duration") else 0
        thumb = DEFAULT_THUMB
        for t in (info.get("thumbnails") or []):
            if t.get("url"):
                thumb = t["url"]

        return Track(
            id_=info.get("id", "yt"),
            title=(info.get("title") or "Unknown")[:55],
            artist=(info.get("uploader") or info.get("channel") or "YouTube")[:35],
            album="YouTube Video" if video else "YouTube HQ",
            duration=dur,
            url=info["url"],
            thumb=thumb,
        )


# ==============================================================================
# Resolver
# ==============================================================================
async def find_track(query: str, video: bool = False) -> Optional[Track]:
    query = query.strip()
    is_url = query.startswith("http")

    t = await YT.track(query, video)
    if t:
        return t

    if not is_url and not video:
        try:
            t = await saavn.get_first_result(query)
            if t:
                logger.info(f"✅ Saavn → {t.title}")
                return t
        except Exception:
            pass
    return None
    # ==============================================================================
# Real LoFi Effect — ffmpeg pipe, non-blocking, no stream stall
# ==============================================================================
def lofi_local_media(url: str) -> str:
    """
    Build an ffmpeg command that pipes a real lofi-filtered audio stream.
    Runs in its own process; pytgcalls reads from the pipe, so the VC
    itself never blocks on ffmpeg's CPU work — that's what fixes the 'ruk jata h' stall.
    """
    filters_chain = (
        "asetrate=44100*0.92,"
        "atempo=1.03,"          # counter the pitch/tempo shift from asetrate so it doesn't drag
        "lowpass=f=3200,"
        "aecho=0.8:0.7:40:0.25,"
        "bass=g=4:f=110:w=0.6"
    )
    return (
        f"ffmpeg -nostdin -re -i \"{url}\" "
        f"-vn -af \"{filters_chain}\" "
        f"-f s16le -ac 2 -ar 48000 -acodec pcm_s16le pipe:1"
    )


def build_media(url: str, cid: int, is_video: bool) -> MediaStream:
    """
    Central place that decides audio path (raw url vs lofi ffmpeg pipe).
    -re flag on ffmpeg reads at native frame rate, which is what stops
    buffering-related stalls compared to reading the whole file at once.
    """
    if is_video:
        return MediaStream(
            url,
            audio_parameters=AudioQuality.STUDIO,
            video_parameters=VideoQuality.HD_720p,
        )

    if cid in LOFI_CHATS:
        return MediaStream(
            lofi_local_media(url),
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,
        )

    return MediaStream(
        url,
        audio_parameters=AudioQuality.STUDIO,
        video_flags=MediaStream.Flags.IGNORE,
    )


# ==============================================================================
# Clean Bold UI
# ==============================================================================
def card(track: Track, by: str, state: ChatState, cid: int, is_video: bool, ai_picked: bool = False) -> str:
    dur = track.duration_str
    src = "📹 VIDEO" if is_video else ("🎧 YT HQ" if "YouTube" in (track.album or "") else "🎵 SAAVN")
    lofi_tag = " · 🌙 LOFI" if cid in LOFI_CHATS and not is_video else ""
    ai_tag = " · 🤖 AI PICK" if ai_picked else ""
    status = "⏸ PAUSED" if state.is_paused else "▶ PLAYING"
    loop_tag = " · 🔁 LOOP" if state.loop else ""
    qcount = len(state.queue)

    return (
        f"🎶 <b>{track.title}</b>\n"
        f"👤 {track.artist}\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"<b>{status}</b>{loop_tag}\n"
        f"{src} · ⏱ {dur}{lofi_tag}{ai_tag}\n"
        f"📋 Queue: <b>{qcount}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"🙋 <b>{by}</b>"
    )


def btns(state: ChatState, cid: int) -> InlineKeyboardMarkup:
    pp = ("▶", "q_resume") if state.is_paused else ("⏸", "q_pause")
    lp = ("🔁 ✓", "q_loop") if state.loop else ("🔁", "q_loop")
    lofi_on = cid in LOFI_CHATS
    lf = ("🌙 ✓", "q_lofi") if lofi_on else ("🌙", "q_lofi")
    ai_on = state.ai_mode
    ai = ("🤖 ✓", "q_ai") if ai_on else ("🤖", "q_ai")

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp[0], callback_data=pp[1]),
            InlineKeyboardButton("⏭", callback_data="q_skip"),
            InlineKeyboardButton("⏹", callback_data="q_stop"),
        ],
        [
            InlineKeyboardButton(lp[0], callback_data=lp[1]),
            InlineKeyboardButton("🔀", callback_data="q_shuffle"),
            InlineKeyboardButton(lf[0], callback_data=lf[1]),
        ],
        [
            InlineKeyboardButton("📋 Queue", callback_data="q_queue"),
            InlineKeyboardButton(ai[0], callback_data=ai[1]),
        ],
    ])


# ==============================================================================
# Stream Core
# ==============================================================================
async def start_stream(cid: int, track: Track, video: bool = False):
    media = build_media(track.url, cid, video)
    await calls.play(cid, media)


async def send_card(cid: int, state: ChatState, video: bool = False, ai_picked: bool = False):
    if not state.current:
        return
    it = state.current
    cap = card(it.track, it.requested_by, state, cid, video, ai_picked)

    old = NOW_MSG.pop(cid, None)
    if old:
        try:
            await bot.delete_messages(cid, old)
        except Exception:
            pass

    try:
        msg = await bot.send_photo(
            cid, photo=it.track.thumb or DEFAULT_THUMB,
            caption=cap, reply_markup=btns(state, cid),
        )
        NOW_MSG[cid] = msg.id
    except Exception:
        try:
            msg = await bot.send_message(cid, cap, reply_markup=btns(state, cid))
            NOW_MSG[cid] = msg.id
        except Exception:
            pass


async def advance(cid: int):
    nxt = queues.next(cid)

    if not nxt:
        state = queues.get(cid)
        if state.ai_mode:
            await autoplay_next(cid)
            return
        try:
            await calls.leave_call(cid)
        except Exception:
            pass
        NOW_MSG.pop(cid, None)
        return

    try:
        await start_stream(cid, nxt.track, nxt.is_video)
        await send_card(cid, queues.get(cid), nxt.is_video, nxt.ai_picked)
    except Exception as e:
        logger.warning(f"Advance error: {e}")
        queues.get(cid).loop = False
        await asyncio.sleep(0.5)
        await advance(cid)


async def autoplay_next(cid: int):
    """AI mode: queue is empty, pick something automatically and keep the vibe going."""
    if AUTOPLAY_LOCK.get(cid):
        return
    AUTOPLAY_LOCK[cid] = True
    try:
        state = queues.get(cid)
        last = state.current.track if state.current else None
        last_title = last.title if last else "Bollywood hit"
        last_artist = last.artist if last else "various"

        query = await ai_suggest.suggest_next(cid, last_title, last_artist)
        track = await find_track(query, video=False)

        if not track:
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            NOW_MSG.pop(cid, None)
            return

        queues.add(cid, track, "🤖 AI Autoplay", is_video=False, ai_picked=True)
        nxt = queues.next(cid)
        await start_stream(cid, nxt.track, False)
        await send_card(cid, state, False, ai_picked=True)
    except Exception as e:
        logger.warning(f"Autoplay error: {e}")
    finally:
        AUTOPLAY_LOCK[cid] = False


@calls.on_update()
async def on_end(_, update):
    cid = getattr(update, "chat_id", None)
    if type(update).__name__ in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and cid:
        await advance(cid)


# ==============================================================================
# Play Helper
# ==============================================================================
async def _play(cid: int, query: str, by: str, msg: Message, video: bool = False):
    asyncio.create_task(auto_del(msg))

    status = await bot.send_message(cid, "⚡ <b>Searching...</b>")

    t0 = time.time()
    track = await find_track(query, video)
    elapsed = round(time.time() - t0, 1)

    if not track:
        await safe_edit(status, "❌ <b>Not found.</b> Try a different query.")
        await asyncio.sleep(2.5)
        await safe_del(status)
        return

    added, pos = queues.add(cid, track, by, is_video=video, ai_picked=False)
    if not added:
        await safe_edit(status, "⚠️ <b>Queue full.</b>")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    state = queues.get(cid)

    if pos == 0:
        try:
            await start_stream(cid, track, video)
            await safe_del(status)
            await send_card(cid, state, video)
        except NoActiveGroupCall:
            queues.clear(cid)
            await safe_edit(status, "❌ <b>Start voice chat first.</b>")
            await asyncio.sleep(2.5)
            await safe_del(status)
        except Exception as e:
            queues.clear(cid)
            await safe_edit(status, f"❌ <b>Error:</b> <code>{str(e)[:150]}</code>")
            await asyncio.sleep(3)
            await safe_del(status)
    else:
        await safe_edit(status, f"📥 <b>Queued #{pos}</b>\n{track.title} — {track.artist}  ({elapsed}s)")
        await asyncio.sleep(2.5)
        await safe_del(status)


# ==============================================================================
# Commands
# ==============================================================================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, msg: Message):
    if len(msg.command) < 2:
        asyncio.create_task(auto_del(msg))
        await flash(msg.chat.id, "ℹ️ <b>Usage:</b> <code>/play song name</code>")
        return
    query = msg.text.split(None, 1)[1].strip()
    await _play(msg.chat.id, query, uname(msg), msg)


@bot.on_message(filters.command(["vplay", "vp", "video"]) & filters.group)
async def cmd_vplay(_, msg: Message):
    if len(msg.command) < 2:
        asyncio.create_task(auto_del(msg))
        await flash(msg.chat.id, "ℹ️ <b>Usage:</b> <code>/vplay song name</code>")
        return
    query = msg.text.split(None, 1)[1].strip()
    await _play(msg.chat.id, query, uname(msg), msg, video=True)


@bot.on_message(filters.command(["skip", "s"]) & filters.group)
async def cmd_skip(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    s = queues.get(msg.chat.id)
    if not s.is_playing:
        return
    s.loop = False
    await advance(msg.chat.id)


@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def cmd_stop(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    cid = msg.chat.id
    queues.clear(cid)
    ai_suggest.forget_chat(cid)
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
    s = queues.get(msg.chat.id)
    if not s.is_playing or s.is_paused:
        return
    await calls.pause_stream(msg.chat.id)
    s.is_paused = True
    await send_card(msg.chat.id, s)


@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    s = queues.get(msg.chat.id)
    if not s.is_paused:
        return
    await calls.resume_stream(msg.chat.id)
    s.is_paused = False
    await send_card(msg.chat.id, s)


@bot.on_message(filters.command("loop") & filters.group)
async def cmd_loop(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    s = queues.get(msg.chat.id)
    if not s.is_playing:
        return
    s.loop = not s.loop
    await send_card(msg.chat.id, s)


@bot.on_message(filters.command("lofi") & filters.group)
async def cmd_lofi(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    cid = msg.chat.id
    if cid in LOFI_CHATS:
        LOFI_CHATS.discard(cid)
    else:
        LOFI_CHATS.add(cid)

    s = queues.get(cid)
    if s.current:
        try:
            is_video = s.current.is_video
            await start_stream(cid, s.current.track, is_video)
            await send_card(cid, s, is_video, s.current.ai_picked)
        except Exception:
            pass


@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai_toggle(_, msg: Message):
    """Toggle AI autoplay mode on/off for this chat."""
    asyncio.create_task(auto_del(msg))
    cid = msg.chat.id
    s = queues.get(cid)
    s.ai_mode = not s.ai_mode
    await flash(cid, f"🤖 <b>AI Autoplay {'ON' if s.ai_mode else 'OFF'}</b>", seconds=2)
    if s.current:
        await send_card(cid, s, s.current.is_video, s.current.ai_picked)
    elif s.ai_mode and not s.is_playing:
        await autoplay_next(cid)


@bot.on_message(filters.command(["queue", "q"]) & filters.group)
async def cmd_queue(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    cid = msg.chat.id
    s = queues.get(cid)
    if not s.current and not s.queue:
        await flash(cid, "📋 <b>Queue empty.</b>")
        return

    lines = []
    if s.current:
        tag = " 🤖" if s.current.ai_picked else ""
        lines.append(f"▶ <b>{s.current.track.title}</b>{tag}")
    for i, item in enumerate(s.queue[:8], 1):
        tag = " 🤖" if item.ai_picked else ""
        lines.append(f"<b>{i}.</b> {item.track.title}{tag}")
    if len(s.queue) > 8:
        lines.append(f"<i>+{len(s.queue) - 8} more</i>")

    await flash(cid, "\n".join(lines), seconds=6)


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    queues.shuffle(msg.chat.id)


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
    s = queues.get(msg.chat.id)
    if s.current:
        await send_card(msg.chat.id, s, s.current.is_video, s.current.ai_picked)


@bot.on_message(filters.command("cookies"))
async def cmd_ck(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    await flash(msg.chat.id, f"🍪 {'✅' if COOKIES_PATH else '❌'} <code>{COOKIES_PATH or 'None'}</code>", seconds=3)


@bot.on_message(filters.command("reloadcookies"))
async def cmd_rcook(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    if not is_sudo(msg):
        return
    find_cookies()
    await flash(msg.chat.id, f"🔄 {'✅' if COOKIES_PATH else '❌'}")


@bot.on_message(filters.command("ping"))
async def cmd_ping(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    t1 = time.time()
    r = await bot.send_message(msg.chat.id, "...")
    t2 = time.time()
    await safe_edit(r, f"🏓 <b>{round((t2 - t1) * 1000)}ms</b>")
    await asyncio.sleep(2.5)
    await safe_del(r)


@bot.on_message(filters.command("help"))
async def cmd_help(_, msg: Message):
    asyncio.create_task(auto_del(msg))
    await bot.send_message(
        msg.chat.id,
        "🎧 <b>FASTTRACK VC MUSIC</b>\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        "▶ <b>Play</b>\n"
        "/play — audio stream\n"
        "/vplay — video stream\n"
        "/aiplay — toggle AI autoplay\n\n"
        "🎛 <b>Controls</b>\n"
        "/pause /resume /skip /stop\n"
        "/loop /lofi /shuffle\n\n"
        "📋 <b>Queue</b>\n"
        "/queue /remove /np\n\n"
        "🛠 <b>Tools</b>\n"
        "/ping /cookies",
    )


@bot.on_message(filters.command("start"))
async def cmd_start(_, msg: Message):
    await msg.reply_text(
        "🎧 <b>FASTTRACK VC MUSIC</b>\n\n"
        "Add me to a group, start a voice chat, then:\n"
        "<code>/play song name</code>",
    )


# ==============================================================================
# Callbacks
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^q_"))
async def cb(_, q: CallbackQuery):
    a = q.data
    cid = q.message.chat.id
    s = queues.get(cid)

    try:
        if a == "q_pause":
            if not s.is_playing or s.is_paused:
                return await q.answer("—")
            await calls.pause_stream(cid)
            s.is_paused = True
            await _refresh_card(q, s, cid)
            await q.answer("Paused")

        elif a == "q_resume":
            if not s.is_paused:
                return await q.answer("—")
            await calls.resume_stream(cid)
            s.is_paused = False
            await _refresh_card(q, s, cid)
            await q.answer("Resumed")

        elif a == "q_skip":
            if not s.is_playing:
                return await q.answer("—")
            s.loop = False
            await q.answer("Skipped")
            await safe_del(q.message)
            await advance(cid)

        elif a == "q_stop":
            queues.clear(cid)
            ai_suggest.forget_chat(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            await safe_del(q.message)
            NOW_MSG.pop(cid, None)
            await q.answer("Stopped")

        elif a == "q_loop":
            if not s.is_playing:
                return await q.answer("—")
            s.loop = not s.loop
            await _refresh_card(q, s, cid)
            await q.answer(f"Loop {'on' if s.loop else 'off'}")

        elif a == "q_shuffle":
            if not s.queue:
                return await q.answer("Empty")
            queues.shuffle(cid)
            await q.answer("Shuffled")

        elif a == "q_lofi":
            if cid in LOFI_CHATS:
                LOFI_CHATS.discard(cid)
                await q.answer("LoFi OFF")
            else:
                LOFI_CHATS.add(cid)
                await q.answer("🌙 LoFi ON")

            if s.current:
                try:
                    await start_stream(cid, s.current.track, s.current.is_video)
                except Exception:
                    pass
                await _refresh_card(q, s, cid)

        elif a == "q_ai":
            s.ai_mode = not s.ai_mode
            await q.answer(f"AI Autoplay {'ON' if s.ai_mode else 'OFF'}")
            if s.current:
                await _refresh_card(q, s, cid)
            elif s.ai_mode and not s.is_playing:
                await autoplay_next(cid)

        elif a == "q_queue":
            if not s.current and not s.queue:
                return await q.answer("Empty")
            lines = []
            if s.current:
                lines.append(f"▶ {s.current.track.title}")
            for i, item in enumerate(s.queue[:6], 1):
                lines.append(f"{i}. {item.track.title}")
            if len(s.queue) > 6:
                lines.append(f"+{len(s.queue) - 6}")
            await q.answer("\n".join(lines), show_alert=True)

    except Exception as e:
        logger.exception(f"CB {a}: {e}")
        await q.answer("Error")


async def _refresh_card(q: CallbackQuery, s: ChatState, cid: int):
    if not s.current:
        return
    cap = card(s.current.track, s.current.requested_by, s, cid, s.current.is_video, s.current.ai_picked)
    try:
        await q.message.edit_caption(caption=cap, reply_markup=btns(s, cid))
    except Exception:
        pass


# ==============================================================================
# Watchdog
# ==============================================================================
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
                ai_suggest.forget_chat(cid)
                NOW_MSG.pop(cid, None)
        except Exception:
            pass


# ==============================================================================
# Boot
# ==============================================================================
async def boot():
    print("=" * 50)
    print("  FastTrack VC Music — Ultimate")
    print("=" * 50)

    await assistant.start()
    await bot.start()
    await calls.start()

    b = await bot.get_me()
    a = await assistant.get_me()

    print(f"\n  Bot: @{b.username}")
    print(f"  Assistant: {a.first_name} [{a.id}]")
    print(f"  Cookies: {'✅' if COOKIES_PATH else '❌'}")
    print("\n  Ready.\n")

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
            for fn in [saavn.close, ai_suggest.close, bot.stop, assistant.stop]:
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
