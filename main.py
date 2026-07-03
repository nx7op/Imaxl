#!/usr/bin/env python3
"""
FastTrack VC Music Bot — Premium Edition
@stillrahul
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

import httpx
import yt_dlp
import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, ChatState

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
AUTODJ: dict[int, bool] = {}
PLAY_HISTORY: dict[int, list[str]] = {}
AI_HTTP = httpx.AsyncClient(timeout=12)

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
        return "Someone"
    return u.first_name or (f"@{u.username}" if u.username else "User")


async def auto_del(msg: Message, delay: float = 0.3):
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


# ==============================================================================
# AI Song Suggest — Smart, Never Repeats
# ==============================================================================
async def ai_suggest(history: list[str], count: int = 1) -> list[str]:
    """Get AI song suggestions based on play history."""
    recent = ", ".join(history[-8:]) if history else "nothing yet"
    already = ", ".join(history[-15:]) if history else "none"

    prompt = (
        f"You are a Bollywood and Hindi music expert DJ. "
        f"The listener recently enjoyed: {recent}. "
        f"Already played (DO NOT repeat these): {already}. "
        f"Suggest {count} different Hindi/Bollywood/Punjabi songs they would love. "
        f"Give ONLY song names with artist, one per line. "
        f"No numbering, no extra text. Example:\n"
        f"Kesariya Arijit Singh\n"
        f"Excuses AP Dhillon"
    )

    try:
        resp = await AI_HTTP.get(
            f"https://gemini.adi7ya.workers.dev/?q={prompt}"
        )
        if resp.status_code == 200:
            text = resp.text.strip()
            lines = [
                l.strip().strip('"').strip("'").strip()
                for l in text.split("\n")
                if l.strip() and len(l.strip()) > 3 and len(l.strip()) < 80
            ]
            # Remove any that match history
            fresh = [l for l in lines if l.lower() not in
                     [h.lower() for h in history]]
            if fresh:
                logger.info(f"🧠 AI: {fresh[:count]}")
                return fresh[:count]
            if lines:
                return lines[:count]
    except Exception as e:
        logger.warning(f"AI error: {e}")

    # Fallback pool
    pool = [
        "Kesariya Arijit Singh", "Raataan Lambiyan", "Tum Hi Ho",
        "Channa Mereya", "Pehla Nasha", "Dil Se Re AR Rahman",
        "Tujhe Dekha To Ye Jaana Sanam", "Kal Ho Naa Ho",
        "Ae Dil Hai Mushkil", "Ilahi Yeh Jawaani Hai Deewani",
        "Chaiyya Chaiyya", "Kun Faya Kun", "Kabira",
        "Agar Tum Saath Ho", "Hawayein Arijit", "Phir Le Aaya Dil",
        "Excuses AP Dhillon", "Brown Munde", "295 Sidhu",
        "Lover Diljit", "Shape of You", "Blinding Lights",
    ]
    available = [s for s in pool if s.lower() not in
                 [h.lower() for h in history]]
    if not available:
        available = pool
    random.shuffle(available)
    return available[:count]


# ==============================================================================
# Mood Instant Pick
# ==============================================================================
MOODS = {
    "sad": ["Tu Jaane Na", "Channa Mereya", "Kabira", "Agar Tum Sath Ho", "Tujhe Bhula Diya", "Phir Le Aaya Dil"],
    "party": ["Kala Chashma", "Kar Gayi Chull", "Badri Ki Dulhania", "Lungi Dance", "Abhi Toh Party", "London Thumakda"],
    "gym": ["Believer", "Unstoppable", "Till I Collapse", "Remember The Name", "Zinda", "Sultan Title"],
    "lofi": ["Hindi Lofi Chill", "Tum Se Hi Lofi", "Kun Faya Kun Lofi", "Baarishein Lofi", "Aaoge Jab Tum Lofi"],
    "romantic": ["Kesariya", "Tum Hi Ho", "Raataan Lambiyan", "Pehle Bhi Main", "Hawayein", "Tera Ban Jaunga"],
    "devotional": ["Hanuman Chalisa", "Gayatri Mantra", "Achyutam Keshavam", "Om Namah Shivaya"],
    "90s": ["Pehla Nasha", "Tujhe Dekha To", "Kuch Kuch Hota Hai", "Ye Kaali Kaali Aankhen", "Dil To Pagal Hai"],
    "english": ["Shape of You", "Blinding Lights", "Perfect", "Someone You Loved", "Night Changes"],
    "punjabi": ["Excuses", "No Love", "295", "Brown Munde", "Lover", "Tauba Tauba"],
}


def mood_pick(prompt: str) -> str:
    p = prompt.lower()
    for mood, kws in {
        "sad": ["sad", "dard", "rona", "broken", "cry", "dukh"],
        "party": ["party", "dance", "nacho", "club", "dj", "masti"],
        "gym": ["gym", "workout", "energy", "power", "motivation"],
        "lofi": ["lofi", "chill", "relax", "sleep", "study"],
        "romantic": ["romantic", "love", "pyar", "ishq", "mohabbat"],
        "devotional": ["bhajan", "mantra", "god", "pooja", "prayer"],
        "90s": ["90s", "old", "classic", "retro", "purana"],
        "english": ["english", "hollywood", "pop", "edm"],
        "punjabi": ["punjabi", "sidhu", "ap dhillon", "diljit"],
    }.items():
        if any(w in p for w in kws):
            return random.choice(MOODS[mood])
    return random.choice([t for s in MOODS.values() for t in s])


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
    return None


find_cookies()


# ==============================================================================
# YouTube
# ==============================================================================
def clean_yt(url: str) -> str:
    try:
        p = urlparse(url)
        if "youtu.be" in p.netloc:
            v = p.path.strip("/").split("/")[0]
            if len(v) == 11:
                return f"https://www.youtube.com/watch?v={v}"
        if "youtube.com" in p.netloc:
            qs = parse_qs(p.query)
            if "v" in qs:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
            m = re.search(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})", p.path)
            if m:
                return f"https://www.youtube.com/watch?v={m.group(1)}"
    except Exception:
        pass
    return url


class YT:
    """Ultra fast YouTube engine — single best strategy."""

    @staticmethod
    def _opts(fmt: str, use_cookies: bool = True) -> dict:
        o = {
            "format": fmt,
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            "socket_timeout": 10,
            "retries": 1,
            "cachedir": False,
            "source_address": "0.0.0.0",
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv_embedded", "mweb"],
                    "player_skip": ["webpage", "js"],
                }
            },
        }
        if use_cookies and COOKIES_PATH:
            o["cookiefile"] = COOKIES_PATH
        return o

    @staticmethod
    def _get(q: str, vid: bool = False) -> Optional[dict]:
        if "youtu" in q:
            q = clean_yt(q)
        fmt = "best" if vid else "bestaudio/best"

        # Try with cookies first
        for use_ck in ([True, False] if COOKIES_PATH else [False]):
            try:
                with yt_dlp.YoutubeDL(YT._opts(fmt, use_ck)) as ydl:
                    info = ydl.extract_info(q, download=False)
                if not info:
                    continue
                if "entries" in info:
                    e = [x for x in (info.get("entries") or []) if x]
                    if not e:
                        continue
                    info = e[0]
                if info.get("url"):
                    return info
            except Exception:
                continue
        return None

    @classmethod
    async def track(cls, q: str, vid: bool = False) -> Optional[Track]:
        info = await asyncio.to_thread(cls._get, q, vid)
        if not info:
            return None
        dur = int(info.get("duration") or 0)
        th = DEFAULT_THUMB
        for t in (info.get("thumbnails") or []):
            if t.get("url"):
                th = t["url"]
        if info.get("thumbnail"):
            th = info["thumbnail"]
        return Track(
            id_=info.get("id", "yt"),
            title=(info.get("title") or "Unknown")[:55],
            artist=(info.get("uploader") or info.get("channel") or "YouTube")[:35],
            album="YouTube Video" if vid else "YouTube HQ",
            duration=dur,
            url=info["url"],
            thumb=th,
        )


# ==============================================================================
# Resolver — Instant
# ==============================================================================
async def find_track(q: str, vid: bool = False, force_yt: bool = False) -> Optional[Track]:
    q = q.strip()
    t = await YT.track(q, vid)
    if t:
        return t
    if not q.startswith("http") and not vid and not force_yt:
        try:
            t = await saavn.get_first_result(q)
            if t:
                return t
        except Exception:
            pass
    return None


# ==============================================================================
# Premium UI — Bold, Clean, Human
# ==============================================================================
OWNER = "@stillrahul"


def make_card(track: Track, by: str, state: ChatState, cid: int,
              vid: bool = False) -> str:
    dur = getattr(track, "duration_str", None) or f"{track.duration}s"

    if vid:
        src = "📹  Video Stream"
    elif "Saavn" in (track.album or ""):
        src = "🎶  JioSaavn"
    else:
        src = "🎧  YouTube HQ"

    parts = [src, dur]
    if state.is_paused:
        parts.append("Paused ⏸")
    if state.loop:
        parts.append("Loop 🔁")
    if cid in LOFI_CHATS:
        parts.append("LoFi 🌙")
    if AUTODJ.get(cid):
        parts.append("Auto-DJ 🤖")

    info_line = "  ·  ".join(parts)
    q_count = len(state.queue)

    return (
        f"<b>🎵  {track.title}</b>\n"
        f"<b>     {track.artist}</b>\n\n"
        f"{info_line}\n"
        f"{'📋  ' + str(q_count) + ' in queue' if q_count else ''}\n\n"
        f"<b>Played by {by}</b>\n"
        f"<b>Powered by {OWNER}</b>"
    )


def make_buttons(state: ChatState, cid: int) -> InlineKeyboardMarkup:
    if state.is_paused:
        pp_text, pp_cb = "Resume ▶", "q_rs"
    else:
        pp_text, pp_cb = "Pause ⏸", "q_ps"

    loop_text = "Loop ✅" if state.loop else "Loop 🔁"
    lofi_text = "LoFi ✅" if cid in LOFI_CHATS else "LoFi 🌙"
    dj_text = "Auto-DJ ✅" if AUTODJ.get(cid) else "Auto-DJ 🤖"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp_text, callback_data=pp_cb),
            InlineKeyboardButton("Skip ⏭", callback_data="q_sk"),
            InlineKeyboardButton("Stop ⏹", callback_data="q_st"),
        ],
        [
            InlineKeyboardButton(loop_text, callback_data="q_lp"),
            InlineKeyboardButton(lofi_text, callback_data="q_lo"),
            InlineKeyboardButton("Shuffle 🔀", callback_data="q_sh"),
        ],
        [
            InlineKeyboardButton(dj_text, callback_data="q_dj"),
            InlineKeyboardButton("Queue 📋", callback_data="q_q"),
            InlineKeyboardButton("Remove 🗑", callback_data="q_rm"),
        ],
        [
            InlineKeyboardButton(f"✨ {OWNER}", url="https://t.me/stillrahul"),
        ],
    ])


# ==============================================================================
# Stream Engine
# ==============================================================================
async def go_stream(cid: int, track: Track, vid: bool = False):
    if vid:
        await calls.play(cid, MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_parameters=VideoQuality.HD_720p,
        ))
    else:
        await calls.play(cid, MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,
        ))


async def show_card(cid: int, state: ChatState, vid: bool = False):
    if not state.current:
        return

    # Delete old card
    old = NOW_MSG.pop(cid, None)
    if old:
        try:
            await bot.delete_messages(cid, old)
        except Exception:
            pass

    it = state.current
    cap = make_card(it.track, it.requested_by, state, cid, vid)

    try:
        msg = await bot.send_photo(
            cid, photo=it.track.thumb or DEFAULT_THUMB,
            caption=cap, reply_markup=make_buttons(state, cid),
        )
        NOW_MSG[cid] = msg.id
    except Exception:
        try:
            msg = await bot.send_message(
                cid, cap, reply_markup=make_buttons(state, cid)
            )
            NOW_MSG[cid] = msg.id
        except Exception:
            pass


# ==============================================================================
# Auto-DJ Engine — Pre-fills queue with 2 songs
# ==============================================================================
async def autodj_fill(cid: int):
    """Pre-fill queue with 2 AI-suggested songs."""
    if not AUTODJ.get(cid):
        return

    state = queues.get(cid)
    needed = 2 - len(state.queue)
    if needed <= 0:
        return

    history = PLAY_HISTORY.get(cid, [])
    suggestions = await ai_suggest(history, count=needed)

    for song_name in suggestions:
        track = await find_track(song_name)
        if track:
            added, _ = queues.add(cid, track, "🤖 Auto-DJ")
            if added:
                logger.info(f"🤖 DJ queued: {track.title}")
                if cid not in PLAY_HISTORY:
                    PLAY_HISTORY[cid] = []
                PLAY_HISTORY[cid].append(track.title)


async def advance(cid: int):
    nxt = queues.next(cid)

    if not nxt:
        # Auto-DJ: fill and try again
        if AUTODJ.get(cid):
            await autodj_fill(cid)
            nxt = queues.next(cid)

    if not nxt:
        try:
            await calls.leave_call(cid)
        except Exception:
            pass
        NOW_MSG.pop(cid, None)
        return

    try:
        vid = "Video" in (nxt.track.album or "")
        await go_stream(cid, nxt.track, vid)

        # Track for AI learning
        if cid not in PLAY_HISTORY:
            PLAY_HISTORY[cid] = []
        PLAY_HISTORY[cid].append(nxt.track.title)
        if len(PLAY_HISTORY[cid]) > 25:
            PLAY_HISTORY[cid] = PLAY_HISTORY[cid][-20:]

        await show_card(cid, queues.get(cid), vid)

        # Pre-fill next songs in background
        asyncio.create_task(autodj_fill(cid))

    except Exception as e:
        logger.warning(f"Stream error: {e}")
        queues.get(cid).loop = False
        await asyncio.sleep(0.5)
        await advance(cid)


@calls.on_update()
async def on_end(_, update):
    cid = getattr(update, "chat_id", None)
    if type(update).__name__ in {
        "StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"
    } and cid:
        await advance(cid)


# ==============================================================================
# Play Core — Ultra Fast, Zero Spam
# ==============================================================================
async def _play(cid: int, q: str, by: str, msg: Message,
                vid: bool = False, force: bool = False):
    asyncio.create_task(auto_del(msg))

    status = await bot.send_message(cid, f"<b>⚡  Searching...</b>")
    t0 = time.time()

    track = await find_track(q, vid, force)
    ms = round((time.time() - t0) * 1000)

    if not track:
        await safe_edit(status, f"<b>❌  Track not found</b>\n<i>Try a different name</i>")
        await asyncio.sleep(3)
        await safe_del(status)
        return

    # History
    if cid not in PLAY_HISTORY:
        PLAY_HISTORY[cid] = []
    PLAY_HISTORY[cid].append(track.title)

    added, pos = queues.add(cid, track, by)
    if not added:
        await safe_edit(status, "<b>⚠️  Queue is full</b>")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    state = queues.get(cid)

    if pos == 0:
        try:
            await go_stream(cid, track, vid)
            await safe_del(status)
            await show_card(cid, state, vid)
            # Pre-fill if autodj on
            asyncio.create_task(autodj_fill(cid))
        except NoActiveGroupCall:
            queues.clear(cid)
            await safe_edit(status,
                "<b>❌  Voice Chat is not active</b>\n"
                "<i>Start a voice chat in this group first</i>")
            await asyncio.sleep(3)
            await safe_del(status)
        except Exception as e:
            queues.clear(cid)
            await safe_edit(status, f"<b>❌  {str(e)[:100]}</b>")
            await asyncio.sleep(3)
            await safe_del(status)
    else:
        await safe_edit(
            status,
            f"<b>📥  Added to queue #{pos}</b>\n"
            f"<b>{track.title}</b> — {track.artist}\n"
            f"<i>{ms}ms</i>"
        )
        await asyncio.sleep(3)
        await safe_del(status)


# ==============================================================================
# Commands
# ==============================================================================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply(
            "<b>🎵  Play a song</b>\n"
            "<code>/play song name</code>\n"
            "<code>/play YouTube URL</code>"
        )
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(3)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m)


@bot.on_message(filters.command(["vplay", "vp", "video"]) & filters.group)
async def cmd_vplay(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply(
            "<b>📹  Play video</b>\n"
            "<code>/vplay song name</code>"
        )
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(3)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m, vid=True)


@bot.on_message(filters.command(["playforce", "pf"]) & filters.group)
async def cmd_pf(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply(
            "<b>🔒  Force YouTube</b>\n"
            "<code>/playforce song name</code>"
        )
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(3)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m, force=True)


@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai(_, m: Message):
    asyncio.create_task(auto_del(m))

    if len(m.command) >= 2:
        pick = mood_pick(m.text.split(None, 1)[1])
    else:
        history = PLAY_HISTORY.get(m.chat.id, [])
        suggestions = await ai_suggest(history, 1)
        pick = suggestions[0] if suggestions else mood_pick("random")

    await _play(m.chat.id, pick, f"🤖 {uname(m)}", m)


@bot.on_message(filters.command("autodj") & filters.group)
async def cmd_autodj(_, m: Message):
    asyncio.create_task(auto_del(m))
    cid = m.chat.id
    AUTODJ[cid] = not AUTODJ.get(cid, False)
    on = AUTODJ[cid]

    r = await m.reply(
        f"<b>🤖  Auto-DJ is {'ON' if on else 'OFF'}</b>\n"
        f"<i>{'AI will keep playing songs for you' if on else 'Stopped auto playing'}</i>"
    )
    await asyncio.sleep(3)
    await safe_del(r)

    if on:
        s = queues.get(cid)
        if not s.is_playing:
            # Start playing immediately
            status = await bot.send_message(cid, "<b>🤖  Auto-DJ starting...</b>")
            history = PLAY_HISTORY.get(cid, [])
            suggestions = await ai_suggest(history, 3)

            started = False
            for song_name in suggestions:
                track = await find_track(song_name)
                if track:
                    if cid not in PLAY_HISTORY:
                        PLAY_HISTORY[cid] = []
                    PLAY_HISTORY[cid].append(track.title)
                    added, pos = queues.add(cid, track, "🤖 Auto-DJ")
                    if added and pos == 0 and not started:
                        try:
                            await go_stream(cid, track)
                            started = True
                        except Exception:
                            pass

            await safe_del(status)
            if started:
                await show_card(cid, queues.get(cid))
        else:
            # Already playing — just pre-fill queue
            asyncio.create_task(autodj_fill(cid))


@bot.on_message(filters.command(["skip", "s"]) & filters.group)
async def cmd_skip(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if s.is_playing:
        s.loop = False
        await advance(m.chat.id)


@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def cmd_stop(_, m: Message):
    asyncio.create_task(auto_del(m))
    cid = m.chat.id
    AUTODJ[cid] = False
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
async def cmd_pause(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if s.is_playing and not s.is_paused:
        await calls.pause_stream(m.chat.id)
        s.is_paused = True
        await show_card(m.chat.id, s)


@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if s.is_paused:
        await calls.resume_stream(m.chat.id)
        s.is_paused = False
        await show_card(m.chat.id, s)


@bot.on_message(filters.command("loop") & filters.group)
async def cmd_loop(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if s.is_playing:
        s.loop = not s.loop
        await show_card(m.chat.id, s)


@bot.on_message(filters.command("lofi") & filters.group)
async def cmd_lofi(_, m: Message):
    asyncio.create_task(auto_del(m))
    cid = m.chat.id
    if cid in LOFI_CHATS:
        LOFI_CHATS.discard(cid)
    else:
        LOFI_CHATS.add(cid)
    s = queues.get(cid)
    if s.current:
        try:
            vid = "Video" in (s.current.track.album or "")
            await go_stream(cid, s.current.track, vid)
            await show_card(cid, s, vid)
        except Exception:
            pass


@bot.on_message(filters.command(["queue", "q"]) & filters.group)
async def cmd_queue(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if not s.current and not s.queue:
        r = await m.reply("<b>📋  Queue is empty</b>")
        await asyncio.sleep(2)
        return await safe_del(r)

    lines = []
    if s.current:
        lines.append(f"<b>▶  {s.current.track.title}</b>  —  {s.current.requested_by}")
    if s.queue:
        for i, it in enumerate(s.queue[:8], 1):
            lines.append(f"<b>{i}.</b>  {it.track.title}")
        if len(s.queue) > 8:
            lines.append(f"\n<i>and {len(s.queue) - 8} more...</i>")

    dj = "\n\n<b>🤖  Auto-DJ is filling the queue</b>" if AUTODJ.get(m.chat.id) else ""

    r = await m.reply("\n".join(lines) + dj)
    await asyncio.sleep(10)
    await safe_del(r)


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, m: Message):
    asyncio.create_task(auto_del(m))
    queues.shuffle(m.chat.id)
    r = await m.reply("<b>🔀  Queue shuffled</b>")
    await asyncio.sleep(2)
    await safe_del(r)


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_rm(_, m: Message):
    asyncio.create_task(auto_del(m))
    if len(m.command) >= 2:
        try:
            it = queues.remove_at(m.chat.id, int(m.command[1]))
            if it:
                r = await m.reply(f"<b>🗑  Removed:</b> {it.track.title}")
                await asyncio.sleep(2)
                await safe_del(r)
        except Exception:
            pass


@bot.on_message(filters.command(["np", "now"]) & filters.group)
async def cmd_np(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if s.current:
        await show_card(m.chat.id, s)


@bot.on_message(filters.command("ping"))
async def cmd_ping(_, m: Message):
    asyncio.create_task(auto_del(m))
    t1 = time.time()
    r = await m.reply("·")
    ms = round((time.time() - t1) * 1000)
    await safe_edit(r,
        f"<b>🏓  {ms}ms</b>\n"
        f"🍪  {'Online' if COOKIES_PATH else 'No cookies'}\n"
        f"🤖  Auto-DJ ready\n\n"
        f"<b>{OWNER}</b>"
    )
    await asyncio.sleep(4)
    await safe_del(r)


@bot.on_message(filters.command("help"))
async def cmd_help(_, m: Message):
    asyncio.create_task(auto_del(m))
    r = await m.reply(
        f"<b>🎵  FastTrack VC Music</b>\n"
        f"<i>Premium music experience for Telegram</i>\n\n"
        f"<b>Play Music</b>\n"
        f"/play — Stream audio\n"
        f"/vplay — Stream video\n"
        f"/playforce — Force YouTube\n"
        f"/aiplay — AI smart play\n"
        f"/autodj — AI keeps playing\n\n"
        f"<b>Controls</b>\n"
        f"/pause  /resume  /skip  /stop\n"
        f"/loop  /lofi  /shuffle\n\n"
        f"<b>Queue</b>\n"
        f"/queue  /remove  /np\n\n"
        f"<b>Built by {OWNER}</b>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✨ {OWNER}", url="https://t.me/stillrahul"),
        ]])
    )
    await asyncio.sleep(20)
    await safe_del(r)


@bot.on_message(filters.command("start"))
async def cmd_start(_, m: Message):
    await m.reply(
        f"<b>🎵  FastTrack VC Music</b>\n\n"
        f"Add me to a group\n"
        f"Start a voice chat\n"
        f"Type <code>/play song name</code>\n\n"
        f"<b>Built by {OWNER}</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✨ {OWNER}", url="https://t.me/stillrahul")],
            [InlineKeyboardButton("Add to Group",
                url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")],
        ])
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
        if a == "q_ps":
            if s.is_playing and not s.is_paused:
                await calls.pause_stream(cid)
                s.is_paused = True
                if s.current:
                    cap = make_card(s.current.track, s.current.requested_by, s, cid)
                    try:
                        await q.message.edit_caption(
                            caption=cap, reply_markup=make_buttons(s, cid))
                    except Exception:
                        pass
            await q.answer("Paused ⏸")

        elif a == "q_rs":
            if s.is_paused:
                await calls.resume_stream(cid)
                s.is_paused = False
                if s.current:
                    cap = make_card(s.current.track, s.current.requested_by, s, cid)
                    try:
                        await q.message.edit_caption(
                            caption=cap, reply_markup=make_buttons(s, cid))
                    except Exception:
                        pass
            await q.answer("Playing ▶")

        elif a == "q_sk":
            if s.is_playing:
                s.loop = False
                await q.answer("Skipping ⏭")
                await safe_del(q.message)
                await advance(cid)
            else:
                await q.answer("Nothing playing")

        elif a == "q_st":
            AUTODJ[cid] = False
            queues.clear(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            await safe_del(q.message)
            NOW_MSG.pop(cid, None)
            await q.answer("Stopped ⏹")

        elif a == "q_lp":
            if s.is_playing:
                s.loop = not s.loop
                if s.current:
                    cap = make_card(s.current.track, s.current.requested_by, s, cid)
                    try:
                        await q.message.edit_caption(
                            caption=cap, reply_markup=make_buttons(s, cid))
                    except Exception:
                        pass
                await q.answer(f"Loop {'on ✅' if s.loop else 'off'}")
            else:
                await q.answer("Nothing playing")

        elif a == "q_lo":
            if cid in LOFI_CHATS:
                LOFI_CHATS.discard(cid)
                await q.answer("LoFi off 🌙")
            else:
                LOFI_CHATS.add(cid)
                await q.answer("LoFi on ✅")
            if s.current:
                cap = make_card(s.current.track, s.current.requested_by, s, cid)
                try:
                    await q.message.edit_caption(
                        caption=cap, reply_markup=make_buttons(s, cid))
                except Exception:
                    pass

        elif a == "q_sh":
            if s.queue:
                queues.shuffle(cid)
                await q.answer("Shuffled 🔀")
            else:
                await q.answer("Queue empty")

        elif a == "q_dj":
            AUTODJ[cid] = not AUTODJ.get(cid, False)
            on = AUTODJ[cid]
            if s.current:
                cap = make_card(s.current.track, s.current.requested_by, s, cid)
                try:
                    await q.message.edit_caption(
                        caption=cap, reply_markup=make_buttons(s, cid))
                except Exception:
                    pass
            await q.answer(f"Auto-DJ {'on ✅' if on else 'off'}")

            if on:
                asyncio.create_task(autodj_fill(cid))

        elif a == "q_q":
            lines = []
            if s.current:
                lines.append(f"▶  {s.current.track.title}")
            for i, it in enumerate(s.queue[:6], 1):
                lines.append(f"{i}.  {it.track.title}")
            if len(s.queue) > 6:
                lines.append(f"+{len(s.queue) - 6} more")
            await q.answer("\n".join(lines) or "Empty", show_alert=True)

        elif a == "q_rm":
            if s.queue:
                it = queues.remove_at(cid, 1)
                await q.answer(
                    f"Removed: {it.track.title}" if it else "Nothing",
                    show_alert=True)
            else:
                await q.answer("Queue empty", show_alert=True)

    except Exception as e:
        logger.exception(f"CB {a}: {e}")
        await q.answer("Error")


# ==============================================================================
# Watchdog
# ==============================================================================
async def watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            for cid in queues.cleanup_idle(
                getattr(config, "AUTO_LEAVE_SECONDS", 180)
            ):
                AUTODJ.pop(cid, None)
                PLAY_HISTORY.pop(cid, None)
                try:
                    await calls.leave_call(cid)
                except Exception:
                    pass
                queues.forget(cid)
                NOW_MSG.pop(cid, None)
        except Exception:
            pass


# ==============================================================================
# Boot
# ==============================================================================
async def boot():
    print("=" * 45)
    print(f"  FastTrack VC Music — Premium")
    print(f"  {OWNER}")
    print("=" * 45)

    await assistant.start()
    await bot.start()
    await calls.start()

    b = await bot.get_me()
    a = await assistant.get_me()

    print(f"\n  Bot: @{b.username}")
    print(f"  Assistant: {a.first_name} [{a.id}]")
    print(f"  Cookies: {'✅' if COOKIES_PATH else '❌'}")
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
            for fn in [saavn.close, bot.stop, assistant.stop, AI_HTTP.aclose]:
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
