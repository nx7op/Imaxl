#!/usr/bin/env python3
"""
================================================================================
 ⚡ FastTrack VC Music Bot — YouTube HQ Edition 2026
 YouTube PRIMARY + JioSaavn Fallback (auto)
 Developer: @stillrahul
================================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sys
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
    sys.exit("❌ pyrofork missing.")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("❌ py-tgcalls missing.")

import yt_dlp
import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, ChatState

# ==============================================================================
# Logging
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(config, "LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("fasttrack.music")

# ==============================================================================
# Clients
# ==============================================================================
bot = Client(
    "vc_music_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True,
)

assistant = Client(
    "vc_music_assistant",
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
NOW_PLAYING_MSG: dict[int, int] = {}

# ==============================================================================
# Owner Helper
# ==============================================================================
def is_owner(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False
    owner_id = getattr(config, "OWNER_ID", 0)
    sudo = getattr(config, "SUDO_USERS", set())
    return (owner_id and user.id == owner_id) or (user.id in sudo)


# ==============================================================================
# AI Mood Database
# ==============================================================================
AI_MOOD_DATABASE = {
    "sad": [
        "tu jaane na atif aslam",
        "channa mereya arijit",
        "kabira encore",
        "agar tum sath ho",
        "tujhe bhula diya",
    ],
    "party": [
        "kala chashma",
        "kar gayi chull",
        "badri ki dulhania",
        "sheila ki jawani",
        "lungi dance",
    ],
    "gym": [
        "believer imagine dragons",
        "unstoppable sia",
        "remember the name",
        "till i collapse eminem",
        "zinda bhaag milkha",
    ],
    "lofi": [
        "hindi lofi chill mix",
        "tum se hi lofi",
        "kun faya kun lofi",
        "baarishein lofi",
        "aaoge jab tum lofi",
    ],
    "romantic": [
        "kesariya arijit",
        "tum hi ho arijit",
        "raataan lambiyan",
        "pehle bhi main",
        "hawayein arijit",
    ],
    "devotional": [
        "hanuman chalisa",
        "om namah shivaya",
        "gayatri mantra",
        "achyutam keshavam",
        "jai mata di bhajan",
    ],
    "90s": [
        "pehla nasha",
        "tujhe dekha to",
        "kuch kuch hota hai",
        "ek ladki ko dekha",
        "ye kaali kaali aankhen",
    ],
}


def analyze_vibe_prompt(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["sad", "dard", "rona", "broken", "cry", "dukh"]):
        return random.choice(AI_MOOD_DATABASE["sad"])
    if any(w in p for w in ["party", "dance", "nacho", "club", "dj"]):
        return random.choice(AI_MOOD_DATABASE["party"])
    if any(w in p for w in ["gym", "workout", "energy", "power", "motivation"]):
        return random.choice(AI_MOOD_DATABASE["gym"])
    if any(w in p for w in ["lofi", "chill", "relax", "sleep", "study"]):
        return random.choice(AI_MOOD_DATABASE["lofi"])
    if any(w in p for w in ["romantic", "love", "pyar", "ishq"]):
        return random.choice(AI_MOOD_DATABASE["romantic"])
    if any(w in p for w in ["bhajan", "devotional", "mantra", "god"]):
        return random.choice(AI_MOOD_DATABASE["devotional"])
    if any(w in p for w in ["90s", "old", "classic", "retro"]):
        return random.choice(AI_MOOD_DATABASE["90s"])
    all_t = [t for sub in AI_MOOD_DATABASE.values() for t in sub]
    return random.choice(all_t)


# ==============================================================================
# Cookies
# ==============================================================================
COOKIES_PATH: Optional[str] = None


def find_cookies() -> Optional[str]:
    global COOKIES_PATH
    base_dir = os.path.dirname(os.path.abspath(__file__))
    paths = [
        "cookies.txt",
        os.path.join(os.getcwd(), "cookies.txt"),
        os.path.join(base_dir, "cookies.txt"),
        "/app/cookies.txt",
    ]
    for path in paths:
        try:
            if os.path.exists(path) and os.path.getsize(path) > 50:
                COOKIES_PATH = path
                logger.info(f"✅ cookies.txt found: {path}")
                return path
        except Exception:
            pass
    logger.warning("⚠️ cookies.txt not found!")
    return None


find_cookies()


# ==============================================================================
# YouTube URL Cleaner
# ==============================================================================
def clean_youtube_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            vid = parsed.path.strip("/").split("/")[0]
            if len(vid) == 11:
                return f"https://www.youtube.com/watch?v={vid}"
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
            match = re.search(
                r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})", parsed.path
            )
            if match:
                return f"https://www.youtube.com/watch?v={match.group(1)}"
    except Exception:
        pass
    return url


# ==============================================================================
# YouTube Engine — Multi Strategy
# ==============================================================================
class YoutubeEngine:

    # Different strategies to try
    STRATEGIES = [
        {
            "name": "tv_embedded (no JS)",
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv_embedded"],
                    "player_skip": ["webpage", "js"],
                }
            },
            "use_cookies": True,
        },
        {
            "name": "web_creator",
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_creator"],
                }
            },
            "use_cookies": True,
        },
        {
            "name": "mweb (mobile web)",
            "extractor_args": {
                "youtube": {
                    "player_client": ["mweb"],
                }
            },
            "use_cookies": True,
        },
        {
            "name": "default (no cookies)",
            "extractor_args": {},
            "use_cookies": False,
        },
        {
            "name": "android (no cookies)",
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                }
            },
            "use_cookies": False,
        },
        {
            "name": "ios (no cookies)",
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios"],
                }
            },
            "use_cookies": False,
        },
    ]

    @classmethod
    def _build_opts(cls, strategy: dict) -> dict:
        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            "socket_timeout": 25,
            "retries": 3,
            "fragment_retries": 3,
            "ignoreerrors": False,
            "cachedir": False,
            "source_address": "0.0.0.0",
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
            },
        }

        if strategy.get("extractor_args"):
            opts["extractor_args"] = strategy["extractor_args"]

        if strategy.get("use_cookies") and COOKIES_PATH:
            opts["cookiefile"] = COOKIES_PATH

        return opts

    @classmethod
    def _extract(cls, query: str) -> Optional[dict]:
        # Clean URL
        if "youtu" in query:
            cleaned = clean_youtube_url(query)
            if cleaned != query:
                logger.info(f"🔗 Cleaned: {cleaned}")
            query = cleaned

        # Try each strategy
        for strategy in cls.STRATEGIES:
            opts = cls._build_opts(strategy)
            name = strategy["name"]

            try:
                logger.info(f"🎬 Trying strategy: {name}")

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(query, download=False)

                if not info:
                    logger.warning(f"⚠️ {name}: No info returned")
                    continue

                # Handle search
                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        logger.warning(f"⚠️ {name}: No entries")
                        continue
                    info = entries[0]

                # Must have URL
                if not info.get("url"):
                    logger.warning(f"⚠️ {name}: No URL")
                    continue

                logger.info(
                    f"✅ Strategy '{name}' worked! → {info.get('title', '?')[:40]}"
                )
                return info

            except yt_dlp.utils.DownloadError as e:
                err = str(e)
                logger.warning(f"⚠️ Strategy '{name}' failed: {err[:100]}")
                continue

            except Exception as e:
                logger.warning(f"⚠️ Strategy '{name}' crashed: {e}")
                continue

        logger.error("❌ All YouTube strategies failed!")
        return None

    @classmethod
    async def get_track(cls, query: str) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query)
        if not info:
            return None

        try:
            duration = int(info.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0

        # Best thumbnail
        thumb = DEFAULT_THUMB
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            try:
                best = max(
                    thumbnails,
                    key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                )
                if best.get("url"):
                    thumb = best["url"]
            except Exception:
                pass
        elif info.get("thumbnail"):
            thumb = info["thumbnail"]

        return Track(
            id_=info.get("id", "yt"),
            title=(info.get("title") or "Unknown")[:50],
            artist=(info.get("uploader") or info.get("channel") or "YouTube")[:35],
            album="YouTube HQ Stream",
            duration=duration,
            url=info["url"],
            thumb=thumb,
        )


# ==============================================================================
# Track Resolver — YT First, Saavn Fallback (auto)
# ==============================================================================
async def resolve_track(query: str) -> Optional[Track]:
    query = query.strip()
    is_url = query.startswith("http://") or query.startswith("https://")

    # YouTube PRIMARY
    logger.info(f"🎯 YouTube: {query[:70]}")
    track = await YoutubeEngine.get_track(query)
    if track:
        return track

    # Saavn FALLBACK — only for text search
    if not is_url:
        logger.info(f"🔄 YT failed → Saavn: {query[:70]}")
        try:
            track = await saavn.get_first_result(query)
            if track:
                logger.info(f"✅ Saavn: {track.title}")
                return track
        except Exception as e:
            logger.warning(f"Saavn error: {e}")

    logger.error(f"❌ All failed: {query[:70]}")
    return None


# ==============================================================================
# UI
# ==============================================================================
def display_name(msg: Message) -> str:
    u = msg.from_user
    if not u:
        return "Anonymous"
    return u.first_name or (f"@{u.username}" if u.username else "User")


def source_badge(track: Track) -> str:
    return "🎬 YouTube HQ" if "YouTube" in (track.album or "") else "🎵 JioSaavn"


def now_playing_card(track: Track, by: str, state: ChatState, cid: int) -> str:
    dsp = DSP_MATRIX.get(cid, "🌌 Pure HQ")
    dur = getattr(track, "duration_str", None) or f"{track.duration}s"
    return (
        f"<b>⚡ FASTTRACK VC MUSIC</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎵 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"📀 <b>Source:</b> {source_badge(track)}\n"
        f"⏱️ <b>Duration:</b> {dur}\n"
        f"🎛️ <b>Sound:</b> {dsp}\n"
        f"📋 <b>Queue:</b> {len(state.queue)} pending\n"
        f"▶️ <b>Status:</b> {'Paused ⏸' if state.is_paused else 'Playing ▶️'}\n"
        f"🔁 <b>Loop:</b> {'ON ✅' if state.loop else 'OFF ❌'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎧 <b>By:</b> {by}\n"
        f"👑 <b>Owner:</b> @stillrahul\n\n"
        f"✨ <i>FastTrack VC Music</i>"
    )


def get_buttons(state: ChatState) -> InlineKeyboardMarkup:
    pp = ("▶️ Resume", "q_resume") if state.is_paused else ("⏸ Pause", "q_pause")
    lp = "🔁 Loop ON" if state.loop else "🔁 Loop OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(pp[0], callback_data=pp[1]),
         InlineKeyboardButton("⏭ Skip", callback_data="q_skip")],
        [InlineKeyboardButton(lp, callback_data="q_loop"),
         InlineKeyboardButton("🔀 Shuffle", callback_data="q_shuffle")],
        [InlineKeyboardButton("📊 Queue", callback_data="q_queue"),
         InlineKeyboardButton("🎛 Sound", callback_data="q_dsp")],
        [InlineKeyboardButton("🗑 Remove", callback_data="q_remove"),
         InlineKeyboardButton("📜 Lyrics", callback_data="q_lyrics")],
        [InlineKeyboardButton("🛑 Stop", callback_data="q_stop")],
        [InlineKeyboardButton("👑 @stillrahul", url="https://t.me/stillrahul")],
    ])


# ==============================================================================
# Stream Core
# ==============================================================================
async def execute_stream(cid: int, track: Track):
    await calls.play(
        cid,
        MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,
        ),
    )


async def send_np(cid: int, state: ChatState):
    if not state.current:
        return
    it = state.current
    cap = now_playing_card(it.track, it.requested_by, state, cid)
    try:
        msg = await bot.send_photo(
            cid, photo=it.track.thumb or DEFAULT_THUMB,
            caption=cap, reply_markup=get_buttons(state),
        )
        NOW_PLAYING_MSG[cid] = msg.id
    except Exception:
        try:
            msg = await bot.send_message(
                cid, cap, reply_markup=get_buttons(state),
            )
            NOW_PLAYING_MSG[cid] = msg.id
        except Exception as e:
            logger.error(f"send_np error: {e}")


async def advance(cid: int):
    nxt = queues.next(cid)
    if not nxt:
        try:
            await calls.leave_call(cid)
        except Exception:
            pass
        NOW_PLAYING_MSG.pop(cid, None)
        return
    try:
        await execute_stream(cid, nxt.track)
        await send_np(cid, queues.get(cid))
    except Exception as e:
        logger.warning(f"advance error: {e}")
        queues.get(cid).loop = False
        await asyncio.sleep(1)
        await advance(cid)


@calls.on_update()
async def on_stream_end(_, update):
    name = type(update).__name__
    cid = getattr(update, "chat_id", None)
    if name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and cid:
        await advance(cid)


# ==============================================================================
# Play helper
# ==============================================================================
async def _play_track(chat_id: int, query: str, requester: str, status_msg):
    track = await resolve_track(query)

    if not track:
        return await status_msg.edit_text(
            "❌ <b>Track not found!</b>\n\n"
            "• Fresh cookies.txt export karo\n"
            "• Video available hona chahiye\n"
            "• Try: <code>/play song name</code>"
        )

    added, pos = queues.add(chat_id, track, requester)
    if not added:
        return await status_msg.edit_text("⚠️ <b>Queue full!</b>")

    state = queues.get(chat_id)

    if pos == 0:
        try:
            await execute_stream(chat_id, track)
            await send_np(chat_id, state)
            await status_msg.delete()
        except NoActiveGroupCall:
            queues.clear(chat_id)
            await status_msg.edit_text(
                "❌ <b>Voice Chat start karo pehle!</b>"
            )
        except Exception as e:
            queues.clear(chat_id)
            await status_msg.edit_text(
                f"❌ <b>Error:</b> <code>{str(e)[:200]}</code>"
            )
    else:
        await status_msg.edit_text(
            f"📥 <b>Queued!</b>\n"
            f"🎵 {track.title}\n"
            f"👤 {track.artist}\n"
            f"🔢 Position: #{pos}"
        )


# ==============================================================================
# Commands
# ==============================================================================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🎵 <b>Usage:</b>\n"
            "<code>/play song name</code>\n"
            "<code>/play YouTube URL</code>"
        )
    query = message.text.split(None, 1)[1].strip()
    status = await message.reply_text("⚡ <b>Fetching...</b>")
    await _play_track(message.chat.id, query, display_name(message), status)


@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🤖 <code>/aiplay mood</code>\n"
            "Moods: sad party gym lofi romantic devotional 90s"
        )
    prompt = message.text.split(None, 1)[1].strip()
    suggested = analyze_vibe_prompt(prompt)
    status = await message.reply_text(
        f"🧠 <b>AI:</b> <code>{suggested}</code>\n⚡ Fetching..."
    )
    await _play_track(
        message.chat.id, suggested,
        f"🤖 AI ({display_name(message)})", status,
    )


@bot.on_message(filters.command(["skip", "s"]) & filters.group)
async def cmd_skip(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.is_playing:
        return await msg.reply_text("❌ Nothing playing!")
    s.loop = False
    await msg.reply_text("⏭ Skipping...")
    await advance(msg.chat.id)


@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def cmd_stop(_, msg: Message):
    queues.clear(msg.chat.id)
    try:
        await calls.leave_call(msg.chat.id)
    except Exception:
        pass
    NOW_PLAYING_MSG.pop(msg.chat.id, None)
    await msg.reply_text("🛑 Stopped!")


@bot.on_message(filters.command("pause") & filters.group)
async def cmd_pause(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.is_playing or s.is_paused:
        return await msg.reply_text("❌ Nothing to pause!")
    await calls.pause_stream(msg.chat.id)
    s.is_paused = True
    await msg.reply_text("⏸ Paused!")


@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.is_paused:
        return await msg.reply_text("❌ Not paused!")
    await calls.resume_stream(msg.chat.id)
    s.is_paused = False
    await msg.reply_text("▶️ Resumed!")


@bot.on_message(filters.command("loop") & filters.group)
async def cmd_loop(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.is_playing:
        return await msg.reply_text("❌ Nothing playing!")
    s.loop = not s.loop
    await msg.reply_text(f"🔁 Loop: {'ON ✅' if s.loop else 'OFF ❌'}")


@bot.on_message(filters.command(["queue", "q"]) & filters.group)
async def cmd_queue(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.current and not s.queue:
        return await msg.reply_text("📋 Queue empty!")
    lines = ["<b>📋 QUEUE</b>\n━━━━━━━━━━━━━━━"]
    if s.current:
        lines.append(f"▶️ <b>Playing:</b> {s.current.track.title}")
    if s.queue:
        lines.append("\n<b>Up Next:</b>")
        for i, item in enumerate(s.queue[:10], 1):
            lines.append(f"<b>{i}.</b> {item.track.title}")
        if len(s.queue) > 10:
            lines.append(f"<i>...+{len(s.queue) - 10} more</i>")
    await msg.reply_text("\n".join(lines))


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.queue:
        return await msg.reply_text("❌ Queue empty!")
    queues.shuffle(msg.chat.id)
    await msg.reply_text("🔀 Shuffled!")


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_remove(_, msg: Message):
    if len(msg.command) < 2:
        return await msg.reply_text("<code>/remove position</code>")
    try:
        pos = int(msg.command[1])
    except ValueError:
        return await msg.reply_text("❌ Invalid number!")
    item = queues.remove_at(msg.chat.id, pos)
    if item:
        await msg.reply_text(f"🗑 Removed: {item.track.title}")
    else:
        await msg.reply_text(f"❌ No track at #{pos}")


@bot.on_message(filters.command(["np", "now"]) & filters.group)
async def cmd_np(_, msg: Message):
    s = queues.get(msg.chat.id)
    if not s.current:
        return await msg.reply_text("❌ Nothing playing!")
    await send_np(msg.chat.id, s)


@bot.on_message(filters.command("cookies"))
async def cmd_cookies(_, msg: Message):
    await msg.reply_text(
        f"🍪 <b>Status:</b> {'✅' if COOKIES_PATH else '❌'}\n"
        f"📁 <b>Path:</b> <code>{COOKIES_PATH or 'None'}</code>"
    )


@bot.on_message(filters.command("reloadcookies"))
async def cmd_reload(_, msg: Message):
    if not is_owner(msg):
        return await msg.reply_text("❌ Owner only!")
    p = find_cookies()
    await msg.reply_text(
        f"🔄 Reloaded!\n{'✅' if p else '❌'} {p or 'Not found'}"
    )


@bot.on_message(filters.command("ping"))
async def cmd_ping(_, msg: Message):
    t1 = asyncio.get_event_loop().time()
    m = await msg.reply_text("🏓...")
    t2 = asyncio.get_event_loop().time()
    await m.edit_text(
        f"🏓 <b>Pong!</b> <code>{round((t2-t1)*1000,2)}ms</code>\n"
        f"🍪 Cookies: {'✅' if COOKIES_PATH else '❌'}"
    )


@bot.on_message(filters.command("help"))
async def cmd_help(_, msg: Message):
    await msg.reply_text(
        "<b>⚡ FastTrack VC Music Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎬 Playback</b>\n"
        "/play — Play song/URL\n"
        "/aiplay — AI mood play\n"
        "/pause — Pause\n"
        "/resume — Resume\n"
        "/skip — Skip\n"
        "/stop — Stop & leave\n"
        "/loop — Toggle loop\n"
        "/np — Now playing\n\n"
        "<b>📋 Queue</b>\n"
        "/queue — View queue\n"
        "/shuffle — Shuffle\n"
        "/remove — Remove track\n\n"
        "<b>🛠 Tools</b>\n"
        "/ping — Bot status\n"
        "/cookies — Check cookies\n"
        "/reloadcookies — Reload\n\n"
        "👑 Owner: @stillrahul",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 Owner", url="https://t.me/stillrahul")
        ]])
    )


@bot.on_message(filters.command("start"))
async def cmd_start(_, msg: Message):
    await msg.reply_text(
        "<b>⚡ FastTrack VC Music Bot</b>\n\n"
        "Group me add karo → VC start karo → /play\n\n"
        "👑 @stillrahul",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 Owner", url="https://t.me/stillrahul"),
            InlineKeyboardButton("📖 Help", callback_data="show_help"),
        ]])
    )


# ==============================================================================
# Callbacks
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^q_|^show_help$"))
async def cb_handler(_, q: CallbackQuery):
    a = q.data
    cid = q.message.chat.id

    if a == "show_help":
        return await q.answer("Use /help in group!", show_alert=True)

    s = queues.get(cid)

    try:
        if a == "q_pause":
            if not s.is_playing or s.is_paused:
                return await q.answer("Nothing to pause!", show_alert=True)
            await calls.pause_stream(cid)
            s.is_paused = True
            await q.message.edit_reply_markup(get_buttons(s))
            await q.answer("⏸ Paused")

        elif a == "q_resume":
            if not s.is_paused:
                return await q.answer("Already playing!", show_alert=True)
            await calls.resume_stream(cid)
            s.is_paused = False
            await q.message.edit_reply_markup(get_buttons(s))
            await q.answer("▶️ Resumed")

        elif a == "q_skip":
            if not s.is_playing:
                return await q.answer("Nothing!", show_alert=True)
            s.loop = False
            await q.answer("⏭ Skipping...")
            try:
                await q.message.delete()
            except Exception:
                pass
            await advance(cid)

        elif a == "q_loop":
            if not s.is_playing:
                return await q.answer("Nothing!", show_alert=True)
            s.loop = not s.loop
            if s.current:
                cap = now_playing_card(s.current.track, s.current.requested_by, s, cid)
                try:
                    await q.message.edit_caption(caption=cap, reply_markup=get_buttons(s))
                except Exception:
                    pass
            await q.answer(f"Loop {'ON' if s.loop else 'OFF'}")

        elif a == "q_shuffle":
            if not s.queue:
                return await q.answer("Queue empty!", show_alert=True)
            queues.shuffle(cid)
            await q.answer("🔀 Shuffled!")

        elif a == "q_queue":
            if not s.current and not s.queue:
                return await q.answer("Empty!", show_alert=True)
            lines = []
            if s.current:
                lines.append(f"▶️ {s.current.track.title}")
            for i, item in enumerate(s.queue[:7], 1):
                lines.append(f"{i}. {item.track.title}")
            if len(s.queue) > 7:
                lines.append(f"...+{len(s.queue)-7}")
            await q.answer("\n".join(lines), show_alert=True)

        elif a == "q_dsp":
            if not s.is_playing:
                return await q.answer("Play first!", show_alert=True)
            profiles = ["🌌 Pure HQ", "🔥 Bass", "🎧 Studio", "🌊 Treble", "🛸 8D"]
            cur = DSP_MATRIX.get(cid, profiles[0])
            nxt = (profiles.index(cur) + 1) % len(profiles) if cur in profiles else 0
            DSP_MATRIX[cid] = profiles[nxt]
            if s.current:
                cap = now_playing_card(s.current.track, s.current.requested_by, s, cid)
                try:
                    await q.message.edit_caption(caption=cap, reply_markup=get_buttons(s))
                except Exception:
                    pass
            await q.answer(f"🎛 {profiles[nxt]}", show_alert=True)

        elif a == "q_remove":
            if not s.queue:
                return await q.answer("Empty!", show_alert=True)
            item = queues.remove_at(cid, 1)
            await q.answer(
                f"🗑 Removed: {item.track.title}" if item else "Nothing!",
                show_alert=True,
            )

        elif a == "q_lyrics":
            if not s.current:
                return await q.answer("Nothing!", show_alert=True)
            await q.answer("📜 Sending...")
            await bot.send_message(
                cid,
                f"📜 <b>{s.current.track.title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Lyrics coming soon! — @stillrahul</i>",
            )

        elif a == "q_stop":
            queues.clear(cid)
            try:
                await calls.leave_call(cid)
            except Exception:
                pass
            try:
                await q.message.delete()
            except Exception:
                pass
            NOW_PLAYING_MSG.pop(cid, None)
            await q.answer("🛑 Stopped!")

    except Exception as e:
        logger.exception(f"CB error [{a}]: {e}")
        await q.answer("❌ Error!", show_alert=True)


# ==============================================================================
# Watchdog
# ==============================================================================
async def watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            idle_chats = queues.cleanup_idle(
                getattr(config, "AUTO_LEAVE_SECONDS", 180)
            )
            for cid in idle_chats:
                try:
                    await calls.leave_call(cid)
                except Exception:
                    pass
                queues.forget(cid)
                NOW_PLAYING_MSG.pop(cid, None)
        except Exception as e:
            logger.error(f"Watchdog: {e}")


# ==============================================================================
# Boot
# ==============================================================================
async def boot():
    print("=" * 60)
    print("  ⚡ FastTrack VC Music — YouTube HQ Edition")
    print("  👑 Owner: @stillrahul")
    print("=" * 60)

    await assistant.start()
    await bot.start()
    await calls.start()

    b = await bot.get_me()
    a = await assistant.get_me()

    print(f"\n🤖 Bot:       @{b.username}")
    print(f"🎵 Assistant: {a.first_name} [{a.id}]")
    print(f"🍪 Cookies:   {'✅ ' + str(COOKIES_PATH) if COOKIES_PATH else '❌'}")
    print(f"🎬 YouTube:   PRIMARY (multi-strategy)")
    print(f"🎵 Saavn:     AUTO FALLBACK")
    print(f"\n✅ Ready!\n")

    asyncio.create_task(watchdog())
    await idle()


def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(boot())
    except KeyboardInterrupt:
        print("\nStopping...")
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
