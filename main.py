#!/usr/bin/env python3
"""
FastTrack VC Music — Premium Edition
Ultra Fast · Zero Spam · Premium UI
Owner: @stillrahul
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

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(config, "LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("fasttrack")

# ── Clients ───────────────────────────────────────────────────────────────────
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
calls   = PyTgCalls(assistant)
saavn   = SaavnClient()
queues  = QueueManager(max_queue_size=getattr(config, "MAX_QUEUE_SIZE", 50))

DEFAULT_THUMB = "https://telegra.ph/file/default_music_thumb.jpg"
LOFI_CHATS: set[int]       = set()
NOW_MSG:    dict[int, int]  = {}
OWNER      = "@stillrahul"
OWNER_URL  = "https://t.me/stillrahul"

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_sudo(msg: Message) -> bool:
    u = msg.from_user
    if not u:
        return False
    oid  = getattr(config, "OWNER_ID", 0)
    sudo = getattr(config, "SUDO_USERS", set())
    return (oid and u.id == oid) or u.id in sudo

def uname(msg: Message) -> str:
    u = msg.from_user
    if not u:
        return "Someone"
    return u.first_name or (f"@{u.username}" if u.username else "User")

async def auto_del(msg: Message, delay: float = 0.4):
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

# ── AI Mood ───────────────────────────────────────────────────────────────────
MOODS = {
    "sad":       ["Tu Jaane Na", "Channa Mereya", "Kabira", "Agar Tum Sath Ho",
                  "Tujhe Bhula Diya", "Phir Le Aaya Dil"],
    "party":     ["Kala Chashma", "Kar Gayi Chull", "Badri Ki Dulhania",
                  "Lungi Dance", "Abhi Toh Party", "London Thumakda"],
    "gym":       ["Believer", "Unstoppable Sia", "Till I Collapse",
                  "Remember The Name", "Zinda", "Sultan Title Track"],
    "lofi":      ["Hindi Lofi Chill Mix", "Tum Se Hi Lofi", "Kun Faya Kun Lofi",
                  "Baarishein Lofi", "Aaoge Jab Tum Lofi"],
    "romantic":  ["Kesariya", "Tum Hi Ho", "Raataan Lambiyan",
                  "Pehle Bhi Main", "Hawayein", "Tera Ban Jaunga"],
    "devotional":["Hanuman Chalisa", "Gayatri Mantra",
                  "Achyutam Keshavam", "Om Namah Shivaya"],
    "90s":       ["Pehla Nasha", "Tujhe Dekha To", "Kuch Kuch Hota Hai",
                  "Ye Kaali Kaali Aankhen", "Dil To Pagal Hai"],
    "punjabi":   ["Excuses AP Dhillon", "No Love", "295 Sidhu",
                  "Brown Munde", "Lover Diljit", "Tauba Tauba"],
    "english":   ["Shape of You", "Blinding Lights", "Perfect",
                  "Someone You Loved", "Night Changes"],
}

def mood_pick(prompt: str) -> str:
    p = prompt.lower()
    MAP = {
        "sad":       ["sad","dard","rona","broken","cry","dukh"],
        "party":     ["party","dance","nacho","club","dj","masti"],
        "gym":       ["gym","workout","energy","power","motivation"],
        "lofi":      ["lofi","chill","relax","sleep","study"],
        "romantic":  ["romantic","love","pyar","ishq","mohabbat"],
        "devotional":["bhajan","mantra","god","pooja","prayer"],
        "90s":       ["90s","old","classic","retro","purana"],
        "punjabi":   ["punjabi","sidhu","ap dhillon","diljit"],
        "english":   ["english","hollywood","pop","edm"],
    }
    for mood, kws in MAP.items():
        if any(w in p for w in kws):
            return random.choice(MOODS[mood])
    return random.choice([t for s in MOODS.values() for t in s])

# ── Cookies ───────────────────────────────────────────────────────────────────
COOKIES_PATH: Optional[str] = None

def find_cookies() -> Optional[str]:
    global COOKIES_PATH
    for p in [
        "cookies.txt",
        "/app/cookies.txt",
        os.path.join(os.path.dirname(__file__), "cookies.txt"),
    ]:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 50:
                COOKIES_PATH = p
                logger.info(f"✅ Cookies: {p}")
                return p
        except Exception:
            pass
    logger.warning("⚠️  No cookies.txt")
    return None

find_cookies()

# ── YouTube URL Cleaner ───────────────────────────────────────────────────────
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

# ── YouTube Engine — Ultra Fast ───────────────────────────────────────────────
class YT:
    """
    Fast-path: tv_embedded (no JS solve needed) + mweb with cookies.
    Falls back to android/default without cookies so we never hang.
    """
    _STRATEGIES = [
        {
            "n": "tv_embedded",
            "args": {
                "youtube": {
                    "player_client": ["tv_embedded"],
                    "player_skip":   ["webpage", "js"],
                }
            },
            "ck": True,
        },
        {
            "n": "mweb",
            "args": {"youtube": {"player_client": ["mweb"]}},
            "ck": True,
        },
        {
            "n": "android",
            "args": {"youtube": {"player_client": ["android"]}},
            "ck": False,
        },
        {
            "n": "default",
            "args": {},
            "ck": False,
        },
    ]

    @classmethod
    def _opts(cls, s: dict, fmt: str) -> dict:
        o: dict = {
            "format":             fmt,
            "quiet":              True,
            "no_warnings":        True,
            "default_search":     "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass":         True,
            "noplaylist":         True,
            "socket_timeout":     8,      # ← tight timeout = fast fail
            "retries":            1,      # ← single retry only
            "cachedir":           False,
            "source_address":     "0.0.0.0",
        }
        if s["args"]:
            o["extractor_args"] = s["args"]
        if s["ck"] and COOKIES_PATH:
            o["cookiefile"] = COOKIES_PATH
        return o

    @classmethod
    def _get(cls, q: str, vid: bool = False) -> Optional[dict]:
        if "youtu" in q:
            q = clean_yt(q)
        fmt = "best" if vid else "bestaudio/best"

        for s in cls._STRATEGIES:
            try:
                with yt_dlp.YoutubeDL(cls._opts(s, fmt)) as ydl:
                    info = ydl.extract_info(q, download=False)
                if not info:
                    continue
                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        continue
                    info = entries[0]
                if info.get("url"):
                    logger.info(f"✅  YT/{s['n']} → {info.get('title','?')[:40]}")
                    return info
            except Exception as e:
                logger.debug(f"YT/{s['n']} ✗  {str(e)[:60]}")
        return None

    @classmethod
    async def track(cls, q: str, vid: bool = False) -> Optional[Track]:
        info = await asyncio.to_thread(cls._get, q, vid)
        if not info:
            return None
        dur = int(info.get("duration") or 0)
        # pick highest-res thumbnail
        thumb = info.get("thumbnail") or DEFAULT_THUMB
        for t in reversed(info.get("thumbnails") or []):
            if t.get("url"):
                thumb = t["url"]
                break
        return Track(
            id_    = info.get("id", "yt"),
            title  = (info.get("title")   or "Unknown")[:55],
            artist = (info.get("uploader") or info.get("channel") or "YouTube")[:35],
            album  = "YouTube Video" if vid else "YouTube HQ",
            duration = dur,
            url    = info["url"],
            thumb  = thumb,
        )

# ── Resolver ──────────────────────────────────────────────────────────────────
async def find_track(q: str, vid: bool = False) -> Optional[Track]:
    q = q.strip()
    t = await YT.track(q, vid)
    if t:
        return t
    # Saavn fallback — text queries only
    if not q.startswith("http") and not vid:
        try:
            t = await saavn.get_first_result(q)
            if t:
                logger.info(f"✅  Saavn → {t.title}")
                return t
        except Exception:
            pass
    return None

# ── Premium UI ────────────────────────────────────────────────────────────────
def _dur(track: Track) -> str:
    return getattr(track, "duration_str", None) or f"{track.duration}s"

def _src(track: Track, vid: bool) -> str:
    if vid:                               return "📹  Video"
    if "Saavn" in (track.album or ""):    return "🎶  JioSaavn"
    return "🎧  YouTube HQ"

def make_card(
    track: Track,
    by: str,
    state: ChatState,
    cid: int,
    vid: bool = False,
) -> str:
    badges: list[str] = []
    if state.is_paused:           badges.append("Paused ⏸")
    else:                         badges.append("Playing ▶")
    if state.loop:                badges.append("Loop 🔁")
    if cid in LOFI_CHATS:         badges.append("LoFi 🌙")

    badge_line = "  ·  ".join(badges)
    q_count    = len(state.queue)
    q_line     = f"Up next: {q_count} track{'s' if q_count != 1 else ''}" if q_count else ""

    return (
        f"🎵  <b>{track.title}</b>\n"
        f"      <i>{track.artist}</i>\n\n"
        f"{_src(track, vid)}  ·  {_dur(track)}\n"
        f"{badge_line}\n"
        + (f"{q_line}\n" if q_line else "")
        + f"\n"
        f"Requested by <b>{by}</b>\n"
        f"Powered by <b>{OWNER}</b>"
    )

def make_btns(state: ChatState, cid: int) -> InlineKeyboardMarkup:
    if state.is_paused:
        pp = ("▶  Resume",  "q_rs")
    else:
        pp = ("⏸  Pause",   "q_ps")

    loop_lbl = "🔁  Loop  ✓" if state.loop else "🔁  Loop"
    lofi_lbl = "🌙  LoFi  ✓" if cid in LOFI_CHATS else "🌙  LoFi"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp[0],            callback_data=pp[1]),
            InlineKeyboardButton("⏭  Skip",        callback_data="q_sk"),
            InlineKeyboardButton("⏹  Stop",        callback_data="q_st"),
        ],
        [
            InlineKeyboardButton(loop_lbl,         callback_data="q_lp"),
            InlineKeyboardButton(lofi_lbl,         callback_data="q_lo"),
            InlineKeyboardButton("🔀  Shuffle",    callback_data="q_sh"),
        ],
        [
            InlineKeyboardButton("📋  Queue",      callback_data="q_q"),
            InlineKeyboardButton("🗑  Remove",     callback_data="q_rm"),
        ],
        [
            InlineKeyboardButton(f"✨  {OWNER}",   url=OWNER_URL),
        ],
    ])

# ── Stream Core ───────────────────────────────────────────────────────────────
async def go_stream(cid: int, track: Track, vid: bool = False) -> None:
    if vid:
        await calls.play(cid, MediaStream(
            track.url,
            audio_parameters = AudioQuality.STUDIO,
            video_parameters = VideoQuality.HD_720p,
        ))
    else:
        await calls.play(cid, MediaStream(
            track.url,
            audio_parameters = AudioQuality.STUDIO,
            video_flags      = MediaStream.Flags.IGNORE,
        ))

async def show_card(cid: int, state: ChatState, vid: bool = False) -> None:
    if not state.current:
        return
    it  = state.current
    cap = make_card(it.track, it.requested_by, state, cid, vid)

    # remove old card cleanly
    old = NOW_MSG.pop(cid, None)
    if old:
        try:
            await bot.delete_messages(cid, old)
        except Exception:
            pass

    try:
        msg = await bot.send_photo(
            cid,
            photo        = it.track.thumb or DEFAULT_THUMB,
            caption      = cap,
            reply_markup = make_btns(state, cid),
        )
        NOW_MSG[cid] = msg.id
    except Exception:
        try:
            msg = await bot.send_message(
                cid, cap, reply_markup=make_btns(state, cid)
            )
            NOW_MSG[cid] = msg.id
        except Exception:
            pass

async def advance(cid: int) -> None:
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
        await show_card(cid, queues.get(cid), vid)
    except Exception as e:
        logger.warning(f"advance: {e}")
        queues.get(cid).loop = False
        await asyncio.sleep(0.5)
        await advance(cid)

@calls.on_update()
async def on_end(_, update) -> None:
    cid = getattr(update, "chat_id", None)
    if (
        type(update).__name__ in {
            "StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"
        }
        and cid
    ):
        await advance(cid)

# ── Play Core — zero spam, ultra fast ────────────────────────────────────────
async def _play(
    cid: int,
    q: str,
    by: str,
    msg: Message,
    vid: bool = False,
) -> None:
    asyncio.create_task(auto_del(msg))

    status = await bot.send_message(cid, "⚡  <b>Searching...</b>")
    t0 = time.monotonic()

    track = await find_track(q, vid)
    ms    = round((time.monotonic() - t0) * 1000)

    if not track:
        await safe_edit(
            status,
            "❌  <b>Couldn't find that track.</b>\n"
            "<i>Try a different name or paste the YouTube link.</i>",
        )
        await asyncio.sleep(4)
        await safe_del(status)
        return

    added, pos = queues.add(cid, track, by)
    if not added:
        await safe_edit(status, "⚠️  <b>Queue is full right now.</b>")
        await asyncio.sleep(3)
        await safe_del(status)
        return

    state = queues.get(cid)

    if pos == 0:
        # ── first track — start immediately ──
        try:
            await go_stream(cid, track, vid)
            await safe_del(status)
            await show_card(cid, state, vid)
        except NoActiveGroupCall:
            queues.clear(cid)
            await safe_edit(
                status,
                "❌  <b>No active Voice Chat found.</b>\n"
                "<i>Start a voice chat in this group first.</i>",
            )
            await asyncio.sleep(4)
            await safe_del(status)
        except Exception as e:
            queues.clear(cid)
            await safe_edit(status, f"❌  <b>Stream error:</b> <code>{str(e)[:120]}</code>")
            await asyncio.sleep(4)
            await safe_del(status)
    else:
        # ── queued ──
        await safe_edit(
            status,
            f"📥  <b>Added to queue  #{pos}</b>\n\n"
            f"🎵  <b>{track.title}</b>\n"
            f"      <i>{track.artist}</i>\n\n"
            f"<i>Found in {ms} ms</i>",
        )
        await asyncio.sleep(4)
        await safe_del(status)

# ── Commands ──────────────────────────────────────────────────────────────────
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply(
            "🎵  <b>Play a song</b>\n\n"
            "<code>/play song name</code>\n"
            "<code>/play YouTube URL</code>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"✨  {OWNER}", url=OWNER_URL)]]
            ),
        )
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(5)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m)


@bot.on_message(filters.command(["vplay", "vp"]) & filters.group)
async def cmd_vplay(_, m: Message):
    if len(m.command) < 2:
        r = await m.reply(
            "📹  <b>Play a video</b>\n\n"
            "<code>/vplay song name</code>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"✨  {OWNER}", url=OWNER_URL)]]
            ),
        )
        asyncio.create_task(auto_del(m))
        await asyncio.sleep(5)
        return await safe_del(r)
    await _play(m.chat.id, m.text.split(None, 1)[1], uname(m), m, vid=True)


@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai(_, m: Message):
    asyncio.create_task(auto_del(m))
    if len(m.command) < 2:
        r = await m.reply(
            "🤖  <b>AI Mood Play</b>\n\n"
            "Moods: <code>sad  party  gym  lofi  romantic  90s  punjabi  english</code>\n\n"
            "<code>/aiplay sad</code>",
        )
        await asyncio.sleep(5)
        return await safe_del(r)
    pick = mood_pick(m.text.split(None, 1)[1])
    await _play(m.chat.id, pick, f"🤖  {uname(m)}", m)


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
        r = await m.reply("📋  <b>Queue is empty.</b>")
        await asyncio.sleep(3)
        return await safe_del(r)

    lines: list[str] = []
    if s.current:
        lines.append(f"▶  <b>{s.current.track.title}</b>  —  {s.current.requested_by}")
    for i, it in enumerate(s.queue[:9], 1):
        lines.append(f"<b>{i}.</b>  {it.track.title}")
    if len(s.queue) > 9:
        lines.append(f"<i>… and {len(s.queue) - 9} more</i>")

    r = await m.reply(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"✨  {OWNER}", url=OWNER_URL)]]
        ),
    )
    await asyncio.sleep(10)
    await safe_del(r)


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, m: Message):
    asyncio.create_task(auto_del(m))
    queues.shuffle(m.chat.id)
    r = await m.reply("🔀  <b>Queue shuffled.</b>")
    await asyncio.sleep(2)
    await safe_del(r)


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_rm(_, m: Message):
    asyncio.create_task(auto_del(m))
    if len(m.command) < 2:
        return
    try:
        it = queues.remove_at(m.chat.id, int(m.command[1]))
        if it:
            r = await m.reply(f"🗑  <b>Removed:</b> {it.track.title}")
            await asyncio.sleep(3)
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
    t1  = time.monotonic()
    r   = await m.reply("·")
    ms  = round((time.monotonic() - t1) * 1000)
    await safe_edit(
        r,
        f"🏓  <b>{ms} ms</b>\n\n"
        f"Cookies  {'✅' if COOKIES_PATH else '❌'}\n\n"
        f"<b>{OWNER}</b>",
        markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"✨  {OWNER}", url=OWNER_URL)]]
        ),
    )
    await asyncio.sleep(5)
    await safe_del(r)


@bot.on_message(filters.command("cookies"))
async def cmd_ck(_, m: Message):
    asyncio.create_task(auto_del(m))
    r = await m.reply(
        f"🍪  Cookies  {'✅  Active' if COOKIES_PATH else '❌  Not found'}\n"
        f"<code>{COOKIES_PATH or 'None'}</code>",
    )
    await asyncio.sleep(5)
    await safe_del(r)


@bot.on_message(filters.command("reloadcookies"))
async def cmd_rcook(_, m: Message):
    asyncio.create_task(auto_del(m))
    if not is_sudo(m):
        return
    find_cookies()
    r = await m.reply(f"🔄  {'✅  Loaded' if COOKIES_PATH else '❌  Not found'}")
    await asyncio.sleep(3)
    await safe_del(r)


@bot.on_message(filters.command("help"))
async def cmd_help(_, m: Message):
    asyncio.create_task(auto_del(m))
    r = await m.reply(
        f"<b>🎵  FastTrack VC Music</b>\n"
        f"<i>Premium voice chat music experience</i>\n\n"
        f"<b>Playback</b>\n"
        f"/play    —  Stream audio\n"
        f"/vplay   —  Stream video\n"
        f"/aiplay  —  Smart mood play\n\n"
        f"<b>Controls</b>\n"
        f"/pause  ·  /resume  ·  /skip  ·  /stop\n"
        f"/loop  ·  /lofi  ·  /shuffle\n\n"
        f"<b>Queue</b>\n"
        f"/queue  ·  /remove  ·  /np\n\n"
        f"<b>Tools</b>\n"
        f"/ping  ·  /cookies\n\n"
        f"<b>Built by {OWNER}</b>",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"✨  {OWNER}", url=OWNER_URL)]]
        ),
    )
    await asyncio.sleep(20)
    await safe_del(r)


@bot.on_message(filters.command("start"))
async def cmd_start(_, m: Message):
    me = await bot.get_me()
    await m.reply(
        f"<b>🎵  FastTrack VC Music</b>\n\n"
        f"Add me to a group, start a voice chat,\n"
        f"then type  <code>/play song name</code>.\n\n"
        f"<b>Built by {OWNER}</b>",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"✨  {OWNER}", url=OWNER_URL),
                InlineKeyboardButton(
                    "➕  Add to Group",
                    url=f"https://t.me/{me.username}?startgroup=true",
                ),
            ],
            [InlineKeyboardButton("📖  Help", callback_data="q_help")],
        ]),
    )

# ── Callbacks ─────────────────────────────────────────────────────────────────
async def _refresh_card(q: CallbackQuery, s: ChatState, cid: int) -> None:
    if s.current:
        vid = "Video" in (s.current.track.album or "")
        cap = make_card(s.current.track, s.current.requested_by, s, cid, vid)
        try:
            await q.message.edit_caption(
                caption      = cap,
                reply_markup = make_btns(s, cid),
            )
        except Exception:
            pass


@bot.on_callback_query(filters.regex(r"^q_"))
async def cb(_, q: CallbackQuery):
    a   = q.data
    cid = q.message.chat.id
    s   = queues.get(cid)

    try:
        # ── pause ──────────────────────────────────────────────────────
        if a == "q_ps":
            if s.is_playing and not s.is_paused:
                await calls.pause_stream(cid)
                s.is_paused = True
                await _refresh_card(q, s, cid)
            await q.answer("Paused ⏸")

        # ── resume ─────────────────────────────────────────────────────
        elif a == "q_rs":
            if s.is_paused:
                await calls.resume_stream(cid)
                s.is_paused = False
                await _refresh_card(q, s, cid)
            await q.answer("Playing ▶")

        # ── skip ───────────────────────────────────────────────────────
        elif a == "q_sk":
            if not s.is_playing:
                return await q.answer("Nothing is playing.")
            s.loop = False
            await q.answer("Skipped ⏭")
            await safe_del(q.message)
            await advance(cid)

        # ── stop ───────────────────────────────────────────────────────
        elif a == "q_st":
            queues.clear(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            await safe_del(q.message)
            NOW_MSG.pop(cid, None)
            await q.answer("Stopped ⏹")

        # ── loop ───────────────────────────────────────────────────────
        elif a == "q_lp":
            if not s.is_playing:
                return await q.answer("Nothing is playing.")
            s.loop = not s.loop
            await _refresh_card(q, s, cid)
            await q.answer(f"Loop  {'on 🔁' if s.loop else 'off'}")

        # ── lofi ───────────────────────────────────────────────────────
        elif a == "q_lo":
            if cid in LOFI_CHATS:
                LOFI_CHATS.discard(cid)
                await q.answer("LoFi off")
            else:
                LOFI_CHATS.add(cid)
                await q.answer("LoFi on 🌙")
            await _refresh_card(q, s, cid)

        # ── shuffle ────────────────────────────────────────────────────
        elif a == "q_sh":
            if not s.queue:
                return await q.answer("Queue is empty.")
            queues.shuffle(cid)
            await q.answer("Shuffled 🔀")

        # ── queue view ─────────────────────────────────────────────────
        elif a == "q_q":
            if not s.current and not s.queue:
                return await q.answer("Queue is empty.", show_alert=True)
            lines: list[str] = []
            if s.current:
                lines.append(f"▶  {s.current.track.title}")
            for i, it in enumerate(s.queue[:7], 1):
                lines.append(f"{i}.  {it.track.title}")
            if len(s.queue) > 7:
                lines.append(f"…  +{len(s.queue) - 7} more")
            await q.answer("\n".join(lines), show_alert=True)

        # ── remove ─────────────────────────────────────────────────────
        elif a == "q_rm":
            if not s.queue:
                return await q.answer("Queue is empty.", show_alert=True)
            it = queues.remove_at(cid, 1)
            await q.answer(
                f"Removed:  {it.track.title}" if it else "Nothing removed.",
                show_alert=True,
            )

        # ── inline help ────────────────────────────────────────────────
        elif a == "q_help":
            await q.answer(
                "Add me to a group → start VC → /play song",
                show_alert=True,
            )

    except Exception as e:
        logger.exception(f"CB {a}: {e}")
        await q.answer("Something went wrong.")

# ── Watchdog ──────────────────────────────────────────────────────────────────
async def watchdog() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            idle_s = getattr(config, "AUTO_LEAVE_SECONDS", 180)
            for cid in queues.cleanup_idle(idle_s):
                try:
                    await calls.leave_call(cid)
                except Exception:
                    pass
                queues.forget(cid)
                NOW_MSG.pop(cid, None)
        except Exception:
            pass

# ── Boot ──────────────────────────────────────────────────────────────────────
async def boot() -> None:
    print("=" * 48)
    print(f"  FastTrack VC Music — Premium Edition")
    print(f"  {OWNER}")
    print("=" * 48)

    await assistant.start()
    await bot.start()
    await calls.start()

    b = await bot.get_me()
    a = await assistant.get_me()

    print(f"\n  Bot:        @{b.username}")
    print(f"  Assistant:  {a.first_name}  [{a.id}]")
    print(f"  Cookies:    {'✅' if COOKIES_PATH else '❌  (Saavn fallback active)'}")
    print(f"\n  Ready.\n")

    asyncio.create_task(watchdog())
    await idle()


def main() -> None:
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(boot())
    except KeyboardInterrupt:
        pass
    finally:
        async def _cleanup():
            for fn in [saavn.close, bot.stop, assistant.stop]:
                try:
                    await fn()
                except Exception:
                    pass
        try:
            loop.run_until_complete(_cleanup())
        except Exception:
            pass


if __name__ == "__main__":
    main()
