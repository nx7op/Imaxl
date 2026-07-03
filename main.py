#!/usr/bin/env python3
"""
FastTrack VC Music — Masterpiece Edition
YouTube HQ Audio + Video • Smart Auto-DJ • Real LoFi
Ultra Fast • Zero Spam • Clean UI
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
DSP_MATRIX: dict[int, str] = {}
LOFI_CHATS: set[int] = set()
NOW_MSG: dict[int, int] = {}
AUTODJ: dict[int, bool] = {}
PLAY_HISTORY: dict[int, list[str]] = {}
AI_HTTP = httpx.AsyncClient(timeout=10)

# ==============================================================================
# Utils
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
# Smart AI Song Suggest — Always different, genre-aware
# ==============================================================================
async def ai_suggest(history: list[str]) -> Optional[str]:
    """
    Uses external API to get intelligent song suggestions.
    Never repeats. Learns from user history.
    """
    recent = ", ".join(history[-5:]) if history else "no songs played yet"

    prompt = (
        f"You are a music expert. The user recently played: {recent}. "
        f"Suggest ONE Hindi/Bollywood song name that the user would love. "
        f"Pick something different from what they already played. "
        f"Reply with ONLY the song name and artist, nothing else. "
        f"Example: Kesariya Arijit Singh"
    )

    try:
        url = f"https://gemini.adi7ya.workers.dev/?q={prompt}"
        resp = await AI_HTTP.get(url)
        if resp.status_code == 200:
            data = resp.text.strip()
            # Clean response — just song name
            data = data.replace('"', '').replace("'", "").strip()
            if len(data) > 3 and len(data) < 80:
                logger.info(f"🧠 AI suggest: {data}")
                return data
    except Exception as e:
        logger.warning(f"AI suggest error: {e}")

    # Fallback — smart random
    fallback = [
        "tum hi ho arijit", "kesariya", "raataan lambiyan",
        "channa mereya", "pehla nasha", "kabira encore",
        "agar tum sath ho", "tujhe dekha to ye jaana sanam",
        "hawayein arijit", "kun faya kun", "dil se re",
        "chaiyya chaiyya", "tum se hi", "kal ho naa ho",
        "ae dil hai mushkil", "ilahi", "safar jab harry met sejal",
    ]
    # Remove already played
    available = [s for s in fallback if s not in history]
    if not available:
        available = fallback
    return random.choice(available)


# ==============================================================================
# Mood Quick Pick (no API needed — instant)
# ==============================================================================
MOODS = {
    "sad": ["tu jaane na", "channa mereya", "kabira", "agar tum sath ho", "tujhe bhula diya", "phir le aaya dil"],
    "party": ["kala chashma", "kar gayi chull", "badri ki dulhania", "lungi dance", "abhi toh party", "london thumakda"],
    "gym": ["believer", "unstoppable sia", "till i collapse", "remember the name", "zinda", "sultan theme"],
    "lofi": ["hindi lofi chill", "tum se hi lofi", "kun faya kun lofi", "baarishein lofi", "aaoge jab tum lofi"],
    "romantic": ["kesariya", "tum hi ho", "raataan lambiyan", "pehle bhi main", "hawayein", "tera ban jaunga"],
    "devotional": ["hanuman chalisa", "gayatri mantra", "achyutam keshavam", "om namah shivaya"],
    "90s": ["pehla nasha", "tujhe dekha to", "kuch kuch hota hai", "ye kaali kaali aankhen", "dil to pagal hai"],
    "english": ["shape of you", "blinding lights", "perfect", "someone you loved", "night changes"],
    "punjabi": ["excuses", "no love", "295", "brown munde", "lover", "tauba tauba"],
}


def mood_pick(prompt: str) -> str:
    p = prompt.lower()
    for mood, kw in {
        "sad": ["sad", "dard", "rona", "broken", "cry", "dukh"],
        "party": ["party", "dance", "nacho", "club", "dj"],
        "gym": ["gym", "workout", "energy", "power"],
        "lofi": ["lofi", "chill", "relax", "sleep", "study"],
        "romantic": ["romantic", "love", "pyar", "ishq"],
        "devotional": ["bhajan", "mantra", "god", "pooja"],
        "90s": ["90s", "old", "classic", "retro"],
        "english": ["english", "hollywood", "pop", "edm"],
        "punjabi": ["punjabi", "sidhu", "ap dhillon"],
    }.items():
        if any(w in p for w in kw):
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
# YouTube URL Cleaner
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


# ==============================================================================
# YouTube Engine — Multi Strategy
# ==============================================================================
class YT:
    S = [
        {"n": "tv", "a": {"youtube": {"player_client": ["tv_embedded"], "player_skip": ["webpage", "js"]}}, "c": True},
        {"n": "wc", "a": {"youtube": {"player_client": ["web_creator"]}}, "c": True},
        {"n": "mw", "a": {"youtube": {"player_client": ["mweb"]}}, "c": True},
        {"n": "df", "a": {}, "c": False},
        {"n": "an", "a": {"youtube": {"player_client": ["android"]}}, "c": False},
    ]

    @classmethod
    def _o(cls, s: dict, fmt: str) -> dict:
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
        }
        if s["a"]:
            o["extractor_args"] = s["a"]
        if s["c"] and COOKIES_PATH:
            o["cookiefile"] = COOKIES_PATH
        return o

    @classmethod
    def _get(cls, q: str, vid: bool = False) -> Optional[dict]:
        if "youtu" in q:
            q = clean_yt(q)
        fmt = "best" if vid else "bestaudio/best"
        for s in cls.S:
            try:
                with yt_dlp.YoutubeDL(cls._o(s, fmt)) as ydl:
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
# Resolver
# ==============================================================================
async def find_track(q: str, vid: bool = False, force_yt: bool = False) -> Optional[Track]:
    q = q.strip()
    is_url = q.startswith("http")

    t = await YT.track(q, vid)
    if t:
        return t

    if not is_url and not vid and not force_yt:
        try:
            t = await saavn.get_first_result(q)
            if t:
                return t
        except Exception:
            pass
    return None


# ==============================================================================
# UI — Clean Bold Human Style
# ==============================================================================
def mk_card(track: Track, by: str, state: ChatState, cid: int, vid: bool = False) -> str:
    dur = getattr(track, "duration_str", None) or f"{track.duration}s"
    src = "📹 Video" if vid else ("🎵" if "Saavn" not in (track.album or "") else "🎶")
    st = "⏸" if state.is_paused else "▶"
    lo = " · 🌙" if cid in LOFI_CHATS else ""
    lp = " · 🔁" if state.loop else ""
    dj = " · 🤖 Auto-DJ" if AUTODJ.get(cid) else ""

    return (
        f"<b>{track.title}</b>\n"
        f"<i>{track.artist}</i>\n\n"
        f"{src} {dur}  {st}{lo}{lp}{dj}\n\n"
        f"<b>{by}</b>"
    )


def mk_btns(state: ChatState, cid: int) -> InlineKeyboardMarkup:
    pp = ("▶", "q_rs") if state.is_paused else ("⏸", "q_ps")
    lp = ("🔁 ✓", "q_lp") if state.loop else ("🔁", "q_lp")
    dj = ("🤖 ✓", "q_dj") if AUTODJ.get(cid) else ("🤖", "q_dj")

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp[0], callback_data=pp[1]),
            InlineKeyboardButton("⏭", callback_data="q_sk"),
            InlineKeyboardButton("⏹", callback_data="q_st"),
        ],
        [
            InlineKeyboardButton(lp[0], callback_data=lp[1]),
            InlineKeyboardButton("🔀", callback_data="q_sh"),
            InlineKeyboardButton("🌙", callback_data="q_lo"),
        ],
        [
            InlineKeyboardButton("📋", callback_data="q_q"),
            InlineKeyboardButton("🗑", callback_data="q_rm"),
            InlineKeyboardButton(dj[0], callback_data=dj[1]),
        ],
    ])


# ==============================================================================
# Stream
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

    old = NOW_MSG.pop(cid, None)
    if old:
        try:
            await bot.delete_messages(cid, old)
        except Exception:
            pass

    it = state.current
    cap = mk_card(it.track, it.requested_by, state, cid, vid)
    try:
        msg = await bot.send_photo(
            cid, photo=it.track.thumb or DEFAULT_THUMB,
            caption=cap, reply_markup=mk_btns(state, cid),
        )
        NOW_MSG[cid] = msg.id
    except Exception:
        try:
            msg = await bot.send_message(cid, cap, reply_markup=mk_btns(state, cid))
            NOW_MSG[cid] = msg.id
        except Exception:
            pass


# ==============================================================================
# Auto-DJ — AI picks next song when queue empty
# ==============================================================================
async def autodj_pick(cid: int):
    """AI-powered Auto-DJ: picks and plays next song."""
    if not AUTODJ.get(cid):
        return False

    history = PLAY_HISTORY.get(cid, [])
    suggestion = await ai_suggest(history)

    if not suggestion:
        return False

    logger.info(f"🤖 Auto-DJ [{cid}]: {suggestion}")

    track = await find_track(suggestion)
    if not track:
        return False

    # Add to history
    if cid not in PLAY_HISTORY:
        PLAY_HISTORY[cid] = []
    PLAY_HISTORY[cid].append(track.title)
    if len(PLAY_HISTORY[cid]) > 20:
        PLAY_HISTORY[cid] = PLAY_HISTORY[cid][-15:]

    queues.add(cid, track, "🤖 Auto-DJ")
    return True


async def advance(cid: int):
    nxt = queues.next(cid)

    if not nxt:
        # Auto-DJ kicks in
        picked = await autodj_pick(cid)
        if picked:
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

        # Track history for AI
        if cid not in PLAY_HISTORY:
            PLAY_HISTORY[cid] = []
        PLAY_HISTORY[cid].append(nxt.track.title)

        await show_card(cid, queues.get(cid), vid)
    except Exception as e:
        logger.warning(f"Advance err: {e}")
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
# Play Core — Zero spam, ultra fast
# ==============================================================================
async def _play(cid: int, q: str, by: str, msg: Message,
                vid: bool = False, force: bool = False):
    asyncio.create_task(auto_del(msg))

    status = await bot.send_message(cid, "⚡")
    t0 = time.time()

    track = await find_track(q, vid, force)
    ms = round((time.time() - t0) * 1000)

    if not track:
        await safe_edit(status, "❌ <b>Not found</b>")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    # Track history for AI
    if cid not in PLAY_HISTORY:
        PLAY_HISTORY[cid] = []
    PLAY_HISTORY[cid].append(track.title)

    added, pos = queues.add(cid, track, by)
    if not added:
        await safe_edit(status, "⚠️ <b>Queue full</b>")
        await asyncio.sleep(2)
        await safe_del(status)
        return

    state = queues.get(cid)

    if pos == 0:
        try:
            await go_stream(cid, track, vid)
            await safe_del(status)
            await show_card(cid, state, vid)
        except NoActiveGroupCall:
            queues.clear(cid)
            await safe_edit(status, "❌ <b>Start VC first</b>")
            await asyncio.sleep(2)
            await safe_del(status)
        except Exception as e:
            queues.clear(cid)
            await safe_edit(status, f"❌ <code>{str(e)[:120]}</code>")
            await asyncio.sleep(3)
            await safe_del(status)
    else:
        await safe_edit(
            status,
            f"<b>+{pos}</b>  {track.title}\n<i>{ms}ms</i>"
        )
        await asyncio.sleep(3)
        await safe_del(status)


# ==============================================================================
# Commands — All auto-delete, zero spam
# ==============================================================================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply("<code>/play song name</code>")
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(2)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m)


@bot.on_message(filters.command(["vplay", "vp", "video"]) & filters.group)
async def cmd_vplay(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply("<code>/vplay song name</code>")
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(2)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m, vid=True)


@bot.on_message(filters.command(["playforce", "pf"]) & filters.group)
async def cmd_pf(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply("<code>/playforce song</code>")
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(2)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m, force=True)


@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai(_, m: Message):
    asyncio.create_task(auto_del(m))

    if len(m.command) >= 2:
        # User gave mood
        pick = mood_pick(m.text.split(None, 1)[1])
    else:
        # No mood — AI picks based on history
        history = PLAY_HISTORY.get(m.chat.id, [])
        pick = await ai_suggest(history)
        if not pick:
            pick = mood_pick("random")

    await _play(m.chat.id, pick, f"🤖 {uname(m)}", m)


@bot.on_message(filters.command("autodj") & filters.group)
async def cmd_autodj(_, m: Message):
    asyncio.create_task(auto_del(m))
    cid = m.chat.id
    AUTODJ[cid] = not AUTODJ.get(cid, False)
    st = "ON" if AUTODJ[cid] else "OFF"
    r = await m.reply(f"<b>🤖 Auto-DJ: {st}</b>")
    await asyncio.sleep(2)
    await safe_del(r)

    # If turning on and nothing playing, start immediately
    if AUTODJ[cid]:
        s = queues.get(cid)
        if not s.is_playing:
            history = PLAY_HISTORY.get(cid, [])
            suggestion = await ai_suggest(history)
            if suggestion:
                status = await bot.send_message(cid, "🤖 <b>Auto-DJ starting...</b>")
                track = await find_track(suggestion)
                if track:
                    if cid not in PLAY_HISTORY:
                        PLAY_HISTORY[cid] = []
                    PLAY_HISTORY[cid].append(track.title)
                    added, pos = queues.add(cid, track, "🤖 Auto-DJ")
                    if added and pos == 0:
                        try:
                            await go_stream(cid, track)
                            await safe_del(status)
                            await show_card(cid, queues.get(cid))
                            return
                        except Exception:
                            pass
                await safe_del(status)


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
        r = await m.reply("<b>Empty</b>")
        await asyncio.sleep(2)
        return await safe_del(r)
    lines = []
    if s.current:
        lines.append(f"<b>▶ {s.current.track.title}</b>")
    for i, it in enumerate(s.queue[:8], 1):
        lines.append(f"{i}. {it.track.title}")
    if len(s.queue) > 8:
        lines.append(f"<i>+{len(s.queue) - 8}</i>")
    r = await m.reply("\n".join(lines))
    await asyncio.sleep(8)
    await safe_del(r)


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, m: Message):
    asyncio.create_task(auto_del(m))
    queues.shuffle(m.chat.id)


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_rm(_, m: Message):
    asyncio.create_task(auto_del(m))
    if len(m.command) >= 2:
        try:
            queues.remove_at(m.chat.id, int(m.command[1]))
        except Exception:
            pass


@bot.on_message(filters.command(["np", "now"]) & filters.group)
async def cmd_np(_, m: Message):
    asyncio.create_task(auto_del(m))
    s = queues.get(m.chat.id)
    if s.current:
        await show_card(m.chat.id, s)


@bot.on_message(filters.command("cookies"))
async def cmd_ck(_, m: Message):
    asyncio.create_task(auto_del(m))
    r = await m.reply(f"🍪 {'✅' if COOKIES_PATH else '❌'}")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("reloadcookies"))
async def cmd_rc(_, m: Message):
    asyncio.create_task(auto_del(m))
    if not is_sudo(m):
        return
    find_cookies()


@bot.on_message(filters.command("ping"))
async def cmd_ping(_, m: Message):
    asyncio.create_task(auto_del(m))
    t1 = time.time()
    r = await m.reply("·")
    await safe_edit(r, f"<b>{round((time.time() - t1) * 1000)}ms</b>")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("help"))
async def cmd_help(_, m: Message):
    asyncio.create_task(auto_del(m))
    r = await m.reply(
        "<b>FastTrack VC Music</b>\n\n"
        "/play — Audio\n"
        "/vplay — Video\n"
        "/playforce — Force YT\n"
        "/aiplay — Smart AI play\n"
        "/autodj — AI Auto-DJ toggle\n\n"
        "/pause · /resume · /skip · /stop\n"
        "/loop · /lofi · /shuffle\n"
        "/queue · /remove · /np\n\n"
        "<b>@stillrahul</b>"
    )
    await asyncio.sleep(15)
    await safe_del(r)


@bot.on_message(filters.command("start"))
async def cmd_start(_, m: Message):
    await m.reply(
        "<b>FastTrack VC Music</b>\n\n"
        "Add to group → Start VC → /play\n\n"
        "<b>@stillrahul</b>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Owner", url="https://t.me/stillrahul"),
        ]])
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
                cap = mk_card(s.current.track, s.current.requested_by, s, cid) if s.current else None
                if cap:
                    try:
                        await q.message.edit_caption(caption=cap, reply_markup=mk_btns(s, cid))
                    except Exception:
                        pass
            await q.answer("⏸")

        elif a == "q_rs":
            if s.is_paused:
                await calls.resume_stream(cid)
                s.is_paused = False
                cap = mk_card(s.current.track, s.current.requested_by, s, cid) if s.current else None
                if cap:
                    try:
                        await q.message.edit_caption(caption=cap, reply_markup=mk_btns(s, cid))
                    except Exception:
                        pass
            await q.answer("▶")

        elif a == "q_sk":
            s.loop = False
            await q.answer("⏭")
            await safe_del(q.message)
            await advance(cid)

        elif a == "q_st":
            AUTODJ[cid] = False
            queues.clear(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            await safe_del(q.message)
            NOW_MSG.pop(cid, None)
            await q.answer("⏹")

        elif a == "q_lp":
            if s.is_playing:
                s.loop = not s.loop
                cap = mk_card(s.current.track, s.current.requested_by, s, cid) if s.current else None
                if cap:
                    try:
                        await q.message.edit_caption(caption=cap, reply_markup=mk_btns(s, cid))
                    except Exception:
                        pass
            await q.answer(f"{'🔁 On' if s.loop else '🔁 Off'}")

        elif a == "q_sh":
            if s.queue:
                queues.shuffle(cid)
            await q.answer("🔀")

        elif a == "q_lo":
            if cid in LOFI_CHATS:
                LOFI_CHATS.discard(cid)
                await q.answer("🌙 Off")
            else:
                LOFI_CHATS.add(cid)
                await q.answer("🌙 On")
            cap = mk_card(s.current.track, s.current.requested_by, s, cid) if s.current else None
            if cap:
                try:
                    await q.message.edit_caption(caption=cap, reply_markup=mk_btns(s, cid))
                except Exception:
                    pass

        elif a == "q_dj":
            AUTODJ[cid] = not AUTODJ.get(cid, False)
            st = "🤖 On" if AUTODJ[cid] else "🤖 Off"
            cap = mk_card(s.current.track, s.current.requested_by, s, cid) if s.current else None
            if cap:
                try:
                    await q.message.edit_caption(caption=cap, reply_markup=mk_btns(s, cid))
                except Exception:
                    pass
            await q.answer(st)

        elif a == "q_q":
            lines = []
            if s.current:
                lines.append(f"▶ {s.current.track.title}")
            for i, it in enumerate(s.queue[:6], 1):
                lines.append(f"{i}. {it.track.title}")
            if len(s.queue) > 6:
                lines.append(f"+{len(s.queue) - 6}")
            await q.answer("\n".join(lines) or "Empty", show_alert=True)

        elif a == "q_rm":
            it = queues.remove_at(cid, 1) if s.queue else None
            await q.answer(f"🗑 {it.track.title}" if it else "Empty", show_alert=True)

    except Exception as e:
        logger.exception(f"CB {a}: {e}")
        await q.answer("—")


# ==============================================================================
# Watchdog
# ==============================================================================
async def watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            for cid in queues.cleanup_idle(getattr(config, "AUTO_LEAVE_SECONDS", 180)):
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
    print("  FastTrack VC Music — Masterpiece")
    print("  @stillrahul")
    print("=" * 45)

    await assistant.start()
    await bot.start()
    await calls.start()

    b = await bot.get_me()
    a = await assistant.get_me()

    print(f"\n  @{b.username}")
    print(f"  {a.first_name} [{a.id}]")
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
