#!/usr/bin/env python3
"""
================================================================================
 ⚡ FastTrack VC Music Bot — YouTube HQ Edition 2026
 Core Engine: YouTube PRIMARY (tv_embedded bypass) + JioSaavn FALLBACK
 Developer & System Architect: @stillrahul
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
    sys.exit("❌ Error: pyrofork/pyrogram missing.")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("❌ Error: py-tgcalls missing.")

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

ENABLE_SAAVN_FALLBACK = os.getenv("ENABLE_SAAVN_FALLBACK", "false").lower() in {
    "1", "true", "yes", "on",
}

# ==============================================================================
# Owner Helper
# ==============================================================================
def is_owner(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False
    owner_id = getattr(config, "OWNER_ID", 0)
    sudo = getattr(config, "SUDO_USERS", set())
    if owner_id and user.id == owner_id:
        return True
    if user.id in sudo:
        return True
    return False

# ==============================================================================
# AI Mood Database
# ==============================================================================
AI_MOOD_DATABASE = {
    "sad": [
        "tu jaane na atif aslam",
        "channa mereya arijit singh",
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
        "remember the name fort minor",
        "till i collapse eminem",
        "zinda bhaag milkha bhaag",
    ],
    "lofi": [
        "hindi lofi chill mix",
        "tum se hi lofi",
        "kun faya kun lofi",
        "baarishein lofi",
        "aaoge jab tum lofi",
    ],
    "romantic": [
        "kesariya arijit singh",
        "tum hi ho arijit singh",
        "raataan lambiyan",
        "pehle bhi main",
        "hawayein arijit singh",
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
        "kuch kuch hota hai title song",
        "ek ladki ko dekha",
        "ye kaali kaali aankhen",
    ],
}


def analyze_vibe_prompt(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["sad", "dard", "rona", "broken", "cry", "dukh", "udaas"]):
        return random.choice(AI_MOOD_DATABASE["sad"])
    if any(w in p for w in ["party", "dance", "nacho", "club", "dj"]):
        return random.choice(AI_MOOD_DATABASE["party"])
    if any(w in p for w in ["gym", "workout", "energy", "power", "motivation"]):
        return random.choice(AI_MOOD_DATABASE["gym"])
    if any(w in p for w in ["lofi", "chill", "relax", "sleep", "study"]):
        return random.choice(AI_MOOD_DATABASE["lofi"])
    if any(w in p for w in ["romantic", "love", "pyar", "ishq", "mohabbat"]):
        return random.choice(AI_MOOD_DATABASE["romantic"])
    if any(w in p for w in ["bhajan", "devotional", "mantra", "god", "pooja"]):
        return random.choice(AI_MOOD_DATABASE["devotional"])
    if any(w in p for w in ["90s", "old", "classic", "retro", "purana"]):
        return random.choice(AI_MOOD_DATABASE["90s"])
    all_tracks = [t for sub in AI_MOOD_DATABASE.values() for t in sub]
    return random.choice(all_tracks)


# ==============================================================================
# Cookies Finder
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
        "/app/data/cookies.txt",
    ]
    for path in paths:
        try:
            if os.path.exists(path) and os.path.getsize(path) > 20:
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
        if "youtube.com" in parsed.netloc or "music.youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
            match = re.search(
                r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})", parsed.path
            )
            if match:
                return f"https://www.youtube.com/watch?v={match.group(1)}"
        match = re.search(
            r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})", url
        )
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    except Exception:
        pass
    return url


# ==============================================================================
# YouTube Engine — 2026 tv_embedded Bypass Fix
# ==============================================================================
class YoutubeEngine:

    @staticmethod
    def _extract(query: str) -> Optional[dict]:
        # Clean YouTube URL
        if "youtu" in query:
            cleaned = clean_youtube_url(query)
            if cleaned != query:
                logger.info(f"🔗 Cleaned URL: {cleaned}")
            query = cleaned

        opts = {
            # tv_embedded client does NOT need JS challenge solving
            # This is the KEY fix for "Signature solving failed"
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 5,
            "ignoreerrors": False,
            "cachedir": False,
            "extractor_args": {
                "youtube": {
                    # tv_embedded = Smart TV client, no JS needed!
                    "player_client": ["tv_embedded", "web_creator"],
                    "player_skip": ["webpage", "js"],
                }
            },
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) "
                    "AppleWebKit/538.1 (KHTML, like Gecko) "
                    "Version/6.0 TV Safari/538.1"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
            },
        }

        # Inject cookies if available
        if COOKIES_PATH:
            opts["cookiefile"] = COOKIES_PATH

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)

                if not info:
                    logger.error("❌ YT: No info returned")
                    return None

                # Handle search results
                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        logger.error("❌ YT: No entries in search result")
                        return None
                    info = entries[0]

                # Must have a playable URL
                if not info.get("url"):
                    logger.warning("❌ YT: No playable URL found")
                    return None

                logger.info(f"✅ YT resolved: {info.get('title', 'Unknown')[:50]}")
                return info

        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "Sign in" in err or "bot" in err.lower() or "confirm" in err.lower():
                logger.error("❌ YouTube bot detection! Update cookies.txt")
            elif "unavailable" in err.lower() or "private" in err.lower():
                logger.error("❌ YouTube video unavailable or private")
            elif "format" in err.lower():
                logger.error(f"❌ YouTube format error: {err[:150]}")
            else:
                logger.error(f"❌ YouTube DownloadError: {err[:200]}")
            return None

        except Exception as e:
            logger.error(f"❌ YouTube engine crash: {e}")
            return None

    @classmethod
    async def get_track(cls, query: str) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query)

        if not info:
            return None

        # Duration
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
            id_=info.get("id", "yt_unknown"),
            title=(info.get("title") or "Unknown Track")[:50],
            artist=(
                info.get("uploader")
                or info.get("channel")
                or "YouTube"
            )[:35],
            album="YouTube HQ Stream",
            duration=duration,
            url=info["url"],
            thumb=thumb,
        )


# ==============================================================================
# Track Resolver — YT First, Saavn Fallback
# ==============================================================================
async def resolve_track(
    query: str,
    allow_saavn: bool = ENABLE_SAAVN_FALLBACK
) -> Optional[Track]:
    query = query.strip()
    is_url = query.startswith("http://") or query.startswith("https://")

    # YouTube PRIMARY
    logger.info(f"🎯 YouTube fetch: {query[:70]}")
    track = await YoutubeEngine.get_track(query)

    if track:
        logger.info(f"✅ YouTube resolved: {track.title}")
        return track

    # Saavn FALLBACK — only for text search, not URLs
    if allow_saavn and not is_url:
        logger.info(f"🔄 YT failed → Saavn fallback: {query[:70]}")
        try:
            track = await saavn.get_first_result(query)
            if track:
                logger.info(f"✅ Saavn resolved: {track.title}")
                return track
        except Exception as e:
            logger.warning(f"Saavn error: {e}")

    logger.error(f"❌ All sources failed: {query[:70]}")
    return None


# ==============================================================================
# UI Helpers
# ==============================================================================
def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Anonymous"
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return "User"


def source_badge(track: Track) -> str:
    if "YouTube" in (track.album or ""):
        return "🎬 YouTube HQ"
    return "🎵 JioSaavn"


def quantum_ui_card(
    track: Track,
    requested_by: str,
    state: ChatState,
    chat_id: int,
) -> str:
    loop_status = "ON ✅" if state.loop else "OFF ❌"
    pause_status = "Paused ⏸" if state.is_paused else "Playing ▶️"
    dsp = DSP_MATRIX.get(chat_id, "🌌 Pure HQ")
    dur = getattr(track, "duration_str", None) or f"{track.duration}s"
    queue_len = len(state.queue)

    return (
        f"<b>⚡ FASTTRACK VC MUSIC</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎵 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"📀 <b>Source:</b> {source_badge(track)}\n"
        f"⏱️ <b>Duration:</b> {dur}\n"
        f"🎛️ <b>Sound:</b> {dsp}\n"
        f"📋 <b>Queue:</b> {queue_len} pending\n"
        f"▶️ <b>Status:</b> {pause_status}\n"
        f"🔁 <b>Loop:</b> {loop_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎧 <b>Requested by:</b> {requested_by}\n"
        f"👑 <b>Owner:</b> @stillrahul\n\n"
        f"✨ <i>FastTrack VC Music — YouTube HQ</i>"
    )


def get_buttons(state: ChatState) -> InlineKeyboardMarkup:
    pause_text = "▶️ Resume" if state.is_paused else "⏸ Pause"
    pause_cb = "q_resume" if state.is_paused else "q_pause"
    loop_text = "🔁 Loop ON" if state.loop else "🔁 Loop OFF"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pause_text, callback_data=pause_cb),
            InlineKeyboardButton("⏭ Skip", callback_data="q_skip"),
        ],
        [
            InlineKeyboardButton(loop_text, callback_data="q_loop"),
            InlineKeyboardButton("🔀 Shuffle", callback_data="q_shuffle"),
        ],
        [
            InlineKeyboardButton("📊 Queue", callback_data="q_queue"),
            InlineKeyboardButton("🎛 Sound", callback_data="q_dsp"),
        ],
        [
            InlineKeyboardButton("🗑 Remove Next", callback_data="q_remove"),
            InlineKeyboardButton("📜 Lyrics", callback_data="q_lyrics"),
        ],
        [
            InlineKeyboardButton("🛑 Stop & Leave", callback_data="q_stop"),
        ],
        [
            InlineKeyboardButton("👑 Owner — @stillrahul", url="https://t.me/stillrahul"),
        ],
    ])


# ==============================================================================
# Stream Core
# ==============================================================================
async def execute_stream(chat_id: int, track: Track):
    await calls.play(
        chat_id,
        MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,
        ),
    )


async def send_now_playing(chat_id: int, state: ChatState):
    if not state.current:
        return
    item = state.current
    caption = quantum_ui_card(item.track, item.requested_by, state, chat_id)
    try:
        msg = await bot.send_photo(
            chat_id,
            photo=item.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=get_buttons(state),
        )
        NOW_PLAYING_MSG[chat_id] = msg.id
    except Exception as e:
        logger.warning(f"send_photo failed: {e}")
        try:
            msg = await bot.send_message(
                chat_id,
                caption,
                reply_markup=get_buttons(state),
            )
            NOW_PLAYING_MSG[chat_id] = msg.id
        except Exception as e2:
            logger.error(f"send_message also failed: {e2}")


async def advance_queue(chat_id: int):
    next_item = queues.next(chat_id)
    if next_item is None:
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        NOW_PLAYING_MSG.pop(chat_id, None)
        return

    try:
        await execute_stream(chat_id, next_item.track)
        state = queues.get(chat_id)
        await send_now_playing(chat_id, state)
    except Exception as e:
        logger.warning(f"advance_queue error [{chat_id}]: {e}")
        state = queues.get(chat_id)
        state.loop = False
        await asyncio.sleep(1)
        await advance_queue(chat_id)


@calls.on_update()
async def on_stream_update(_, update):
    name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)
    if name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and chat_id:
        await advance_queue(chat_id)


# ==============================================================================
# Commands
# ==============================================================================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🎵 <b>Usage:</b>\n"
            "<code>/play song name</code>\n"
            "<code>/play YouTube URL</code>\n\n"
            "Example: <code>/play kesariya</code>"
        )

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)

    status = await message.reply_text("⚡ <b>Fetching from YouTube HQ...</b>")
    track = await resolve_track(query)

    if not track:
        return await status.edit_text(
            "❌ <b>YouTube fetch failed!</b>\n\n"
            "<b>Possible reasons:</b>\n"
            "• cookies.txt expired — export fresh cookies\n"
            "• Video private or region blocked\n"
            "• Invalid URL\n\n"
            "Try: <code>/play song name</code>"
        )

    added, position = queues.add(chat_id, track, requester)
    if not added:
        return await status.edit_text("⚠️ <b>Queue full!</b>")

    state = queues.get(chat_id)

    if position == 0:
        try:
            await execute_stream(chat_id, track)
            await send_now_playing(chat_id, state)
            await status.delete()
        except NoActiveGroupCall:
            queues.clear(chat_id)
            await status.edit_text(
                "❌ <b>No Voice Chat active!</b>\n"
                "Start Voice Chat in group first, then /play."
            )
        except Exception as e:
            queues.clear(chat_id)
            logger.exception(f"Stream start error: {e}")
            await status.edit_text(
                f"❌ <b>Stream failed:</b>\n<code>{str(e)[:200]}</code>"
            )
    else:
        await status.edit_text(
            f"📥 <b>Added to Queue!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>Track:</b> {track.title}\n"
            f"👤 <b>Artist:</b> {track.artist}\n"
            f"🔢 <b>Position:</b> #{position}\n"
            f"🎧 <b>By:</b> {requester}"
        )


@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🤖 <b>Usage:</b> <code>/aiplay mood</code>\n\n"
            "<b>Moods:</b> sad, party, gym, lofi, romantic, devotional, 90s\n"
            "Example: <code>/aiplay sad vibe</code>"
        )

    prompt = message.text.split(None, 1)[1].strip()
    suggested = analyze_vibe_prompt(prompt)
    chat_id = message.chat.id
    requester = f"🤖 AI ({display_name(message)})"

    status = await message.reply_text(
        f"🧠 <b>AI Mood Match:</b> <code>{suggested}</code>\n"
        f"⚡ <b>Fetching from YouTube HQ...</b>"
    )

    track = await resolve_track(suggested)

    if not track:
        return await status.edit_text("❌ <b>AI track fetch failed. Try again!</b>")

    added, position = queues.add(chat_id, track, requester)
    if not added:
        return await status.edit_text("⚠️ <b>Queue full!</b>")

    state = queues.get(chat_id)

    if position == 0:
        try:
            await execute_stream(chat_id, track)
            await send_now_playing(chat_id, state)
            await status.delete()
        except NoActiveGroupCall:
            queues.clear(chat_id)
            await status.edit_text("❌ <b>Start Voice Chat first!</b>")
        except Exception as e:
            queues.clear(chat_id)
            await status.edit_text(f"❌ <b>Stream failed:</b> <code>{e}</code>")
    else:
        await status.edit_text(
            f"🤖 <b>AI Queued:</b> {track.title} at #{position}"
        )


@bot.on_message(filters.command(["skip", "s"]) & filters.group)
async def cmd_skip(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing or not state.current:
        return await message.reply_text("❌ <b>Nothing is playing!</b>")
    state.loop = False
    await message.reply_text("⏭ <b>Skipping...</b>")
    await advance_queue(chat_id)


@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def cmd_stop(_, message: Message):
    chat_id = message.chat.id
    queues.clear(chat_id)
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    NOW_PLAYING_MSG.pop(chat_id, None)
    await message.reply_text("🛑 <b>Stopped. Queue cleared.</b>")


@bot.on_message(filters.command("pause") & filters.group)
async def cmd_pause(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing or state.is_paused:
        return await message.reply_text("❌ <b>Nothing to pause!</b>")
    await calls.pause_stream(chat_id)
    state.is_paused = True
    await message.reply_text("⏸ <b>Paused!</b>")


@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_paused:
        return await message.reply_text("❌ <b>Nothing to resume!</b>")
    await calls.resume_stream(chat_id)
    state.is_paused = False
    await message.reply_text("▶️ <b>Resumed!</b>")


@bot.on_message(filters.command("loop") & filters.group)
async def cmd_loop(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing:
        return await message.reply_text("❌ <b>Nothing playing!</b>")
    state.loop = not state.loop
    await message.reply_text(
        f"🔁 <b>Loop:</b> {'ON ✅' if state.loop else 'OFF ❌'}"
    )


@bot.on_message(filters.command(["queue", "q"]) & filters.group)
async def cmd_queue(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.current and not state.queue:
        return await message.reply_text("📋 <b>Queue is empty!</b>")

    lines = ["<b>📋 CURRENT QUEUE</b>\n━━━━━━━━━━━━━━━━━━━━"]
    if state.current:
        lines.append(
            f"▶️ <b>Playing:</b> {state.current.track.title}\n"
            f"   🎧 {state.current.requested_by}"
        )
    if state.queue:
        lines.append("\n<b>Up Next:</b>")
        for idx, item in enumerate(state.queue[:10], 1):
            lines.append(f"<b>{idx}.</b> {item.track.title} — {item.requested_by}")
        if len(state.queue) > 10:
            lines.append(f"\n<i>...and {len(state.queue) - 10} more</i>")

    await message.reply_text("\n".join(lines))


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.queue:
        return await message.reply_text("❌ <b>Queue is empty!</b>")
    queues.shuffle(chat_id)
    await message.reply_text("🔀 <b>Queue shuffled!</b>")


@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_remove(_, message: Message):
    chat_id = message.chat.id
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: <code>/remove position</code>\n"
            "Example: <code>/remove 2</code>"
        )
    try:
        pos = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ <b>Invalid number!</b>")

    item = queues.remove_at(chat_id, pos)
    if item:
        await message.reply_text(f"🗑 <b>Removed:</b> {item.track.title}")
    else:
        await message.reply_text(f"❌ <b>No track at position #{pos}</b>")


@bot.on_message(filters.command(["np", "now"]) & filters.group)
async def cmd_now_playing(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.current:
        return await message.reply_text("❌ <b>Nothing is playing!</b>")
    await send_now_playing(chat_id, state)


@bot.on_message(filters.command("cookies"))
async def cmd_cookies(_, message: Message):
    status_text = "✅ Found" if COOKIES_PATH else "❌ Not Found"
    path = COOKIES_PATH or "None"
    await message.reply_text(
        f"🍪 <b>Cookies Status:</b> {status_text}\n"
        f"📁 <b>Path:</b> <code>{path}</code>\n\n"
        f"Cookies expire hoti hain — fresh export karo YouTube se."
    )


@bot.on_message(filters.command("reloadcookies"))
async def cmd_reload_cookies(_, message: Message):
    if not is_owner(message):
        return await message.reply_text("❌ <b>Only owner can use this!</b>")
    path = find_cookies()
    await message.reply_text(
        f"🔄 <b>Cookies reloaded!</b>\n"
        f"Status: {'✅ Found' if path else '❌ Not Found'}\n"
        f"Path: <code>{path or 'None'}</code>"
    )


@bot.on_message(filters.command("ping"))
async def cmd_ping(_, message: Message):
    start = asyncio.get_event_loop().time()
    msg = await message.reply_text("🏓 Pinging...")
    end = asyncio.get_event_loop().time()
    await msg.edit_text(
        f"🏓 <b>Pong!</b>\n"
        f"⚡ <b>Latency:</b> <code>{round((end - start) * 1000, 2)} ms</code>\n"
        f"🍪 <b>Cookies:</b> {'✅' if COOKIES_PATH else '❌'}\n"
        f"🎵 <b>Saavn Fallback:</b> {'ON' if ENABLE_SAAVN_FALLBACK else 'OFF'}"
    )


@bot.on_message(filters.command("help"))
async def cmd_help(_, message: Message):
    await message.reply_text(
        "<b>⚡ FastTrack VC Music Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎬 Playback</b>\n"
        "/play [song/URL] — Play from YouTube HQ\n"
        "/aiplay [mood] — AI mood-based play\n"
        "/pause — Pause stream\n"
        "/resume — Resume stream\n"
        "/skip — Skip current track\n"
        "/stop — Stop & leave VC\n"
        "/loop — Toggle loop\n"
        "/np — Now playing info\n\n"
        "<b>📋 Queue</b>\n"
        "/queue — View queue\n"
        "/shuffle — Shuffle queue\n"
        "/remove [pos] — Remove track\n\n"
        "<b>🛠 Tools</b>\n"
        "/ping — Bot status\n"
        "/cookies — Cookies status\n"
        "/reloadcookies — Reload cookies\n\n"
        "<b>🤖 AI Moods:</b>\n"
        "sad • party • gym • lofi\n"
        "romantic • devotional • 90s\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Owner:</b> @stillrahul",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 Owner", url="https://t.me/stillrahul")
        ]])
    )


@bot.on_message(filters.command("start"))
async def cmd_start(_, message: Message):
    await message.reply_text(
        "<b>⚡ FastTrack VC Music Bot</b>\n\n"
        "Group mein add karo, Voice Chat start karo, phir:\n"
        "<code>/play song name</code>\n\n"
        "/help — All commands\n\n"
        "👑 Owner: @stillrahul",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 Owner", url="https://t.me/stillrahul"),
            InlineKeyboardButton("📖 Help", callback_data="show_help"),
        ]])
    )


# ==============================================================================
# Callbacks
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^q_|^show_help$"))
async def handle_callbacks(_, query: CallbackQuery):
    action = query.data
    chat_id = query.message.chat.id

    if action == "show_help":
        return await query.answer("Use /help in group!", show_alert=True)

    state = queues.get(chat_id)

    try:
        if action == "q_pause":
            if not state.is_playing or state.is_paused:
                return await query.answer("Nothing to pause!", show_alert=True)
            await calls.pause_stream(chat_id)
            state.is_paused = True
            await query.message.edit_reply_markup(reply_markup=get_buttons(state))
            await query.answer("⏸ Paused")

        elif action == "q_resume":
            if not state.is_paused:
                return await query.answer("Already playing!", show_alert=True)
            await calls.resume_stream(chat_id)
            state.is_paused = False
            await query.message.edit_reply_markup(reply_markup=get_buttons(state))
            await query.answer("▶️ Resumed")

        elif action == "q_skip":
            if not state.is_playing or not state.current:
                return await query.answer("Nothing playing!", show_alert=True)
            state.loop = False
            await query.answer("⏭ Skipping...")
            try:
                await query.message.delete()
            except Exception:
                pass
            await advance_queue(chat_id)

        elif action == "q_loop":
            if not state.is_playing:
                return await query.answer("Nothing playing!", show_alert=True)
            state.loop = not state.loop
            if state.current:
                caption = quantum_ui_card(
                    state.current.track,
                    state.current.requested_by,
                    state,
                    chat_id,
                )
                try:
                    await query.message.edit_caption(
                        caption=caption,
                        reply_markup=get_buttons(state),
                    )
                except Exception:
                    pass
            await query.answer(f"Loop {'ON ✅' if state.loop else 'OFF ❌'}")

        elif action == "q_shuffle":
            if not state.queue:
                return await query.answer("Queue empty!", show_alert=True)
            queues.shuffle(chat_id)
            await query.answer("🔀 Shuffled!")

        elif action == "q_queue":
            if not state.current and not state.queue:
                return await query.answer("Queue empty!", show_alert=True)
            lines = ["📋 QUEUE\n━━━━━━━━━━━━━━━"]
            if state.current:
                lines.append(f"▶️ {state.current.track.title}")
            for i, item in enumerate(state.queue[:7], 1):
                lines.append(f"{i}. {item.track.title}")
            if len(state.queue) > 7:
                lines.append(f"...+{len(state.queue) - 7} more")
            await query.answer("\n".join(lines), show_alert=True)

        elif action == "q_dsp":
            if not state.is_playing:
                return await query.answer("Play a track first!", show_alert=True)
            profiles = [
                "🌌 Pure HQ",
                "🔥 Bass Boost",
                "🎧 Studio Mode",
                "🌊 Crystal Treble",
                "🛸 8D Space",
            ]
            current = DSP_MATRIX.get(chat_id, profiles[0])
            next_idx = (
                (profiles.index(current) + 1) % len(profiles)
                if current in profiles else 0
            )
            DSP_MATRIX[chat_id] = profiles[next_idx]
            if state.current:
                caption = quantum_ui_card(
                    state.current.track,
                    state.current.requested_by,
                    state,
                    chat_id,
                )
                try:
                    await query.message.edit_caption(
                        caption=caption,
                        reply_markup=get_buttons(state),
                    )
                except Exception:
                    pass
            await query.answer(f"🎛 Sound: {profiles[next_idx]}", show_alert=True)

        elif action == "q_remove":
            if not state.queue:
                return await query.answer("Queue empty!", show_alert=True)
            item = queues.remove_at(chat_id, 1)
            if item:
                await query.answer(f"🗑 Removed: {item.track.title}", show_alert=True)
            else:
                await query.answer("Nothing to remove!", show_alert=True)

        elif action == "q_lyrics":
            if not state.current:
                return await query.answer("Nothing playing!", show_alert=True)
            await query.answer("📜 Sending lyrics...")
            await bot.send_message(
                chat_id,
                f"📜 <b>Lyrics:</b> {state.current.track.title}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Lyrics feature coming soon!</i>\n"
                f"<i>Enjoy HQ stream by @stillrahul</i>",
            )

        elif action == "q_stop":
            queues.clear(chat_id)
            try:
                await calls.leave_call(chat_id)
            except Exception:
                pass
            try:
                await query.message.delete()
            except Exception:
                pass
            NOW_PLAYING_MSG.pop(chat_id, None)
            await query.answer("🛑 Stopped!")

    except Exception as e:
        logger.exception(f"Callback error [{action}]: {e}")
        await query.answer("❌ Error occurred!", show_alert=True)


# ==============================================================================
# Watchdog — Auto leave idle VC
# ==============================================================================
async def watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            idle_seconds = getattr(config, "AUTO_LEAVE_SECONDS", 180)
            idle_chats = queues.cleanup_idle(idle_seconds)
            for cid in idle_chats:
                try:
                    await calls.leave_call(cid)
                    logger.info(f"🔇 Auto-left idle VC: {cid}")
                except Exception:
                    pass
                queues.forget(cid)
                NOW_PLAYING_MSG.pop(cid, None)
        except Exception as e:
            logger.error(f"Watchdog error: {e}")


# ==============================================================================
# Boot
# ==============================================================================
async def boot():
    print("=" * 65)
    print("  ⚡ FastTrack VC Music Bot — YouTube HQ Edition")
    print("  👑 Owner: @stillrahul")
    print("=" * 65)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    assistant_me = await assistant.get_me()

    print(f"\n🤖 Bot:        @{bot_me.username}")
    print(f"🎵 Assistant:  {assistant_me.first_name} [{assistant_me.id}]")
    print(f"🍪 Cookies:    {'✅ ' + str(COOKIES_PATH) if COOKIES_PATH else '❌ NOT FOUND'}")
    print(f"🎬 YouTube:    PRIMARY (tv_embedded bypass)")
    print(f"🎵 Saavn:      {'FALLBACK ON' if ENABLE_SAAVN_FALLBACK else 'FALLBACK OFF'}")
    print("\n✅ Ready!\n")

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
            try:
                await saavn.close()
            except Exception:
                pass
            try:
                await bot.stop()
            except Exception:
                pass
            try:
                await assistant.stop()
            except Exception:
                pass
        try:
            loop.run_until_complete(cleanup())
        except Exception:
            pass


if __name__ == "__main__":
    main()
