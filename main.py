#!/usr/bin/env python3
"""
================================================================================
 ⚡ FastTrack VC Music Bot — Quantum AI Hybrid Edition (2026)
 Core Engine: YouTube PRIMARY (Anti-Bot) + JioSaavn FALLBACK
 Developer & System Architect: @stillrahul
================================================================================
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
from typing import Optional

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
NOW_PLAYING_MSG: dict[int, int] = {}  # chat_id -> message_id

# ==============================================================================
# AI Mood Database
# ==============================================================================
AI_MOOD_DATABASE = {
    "sad":      ["tu jaane na", "channa mereya", "kabira", "agar tum sath ho", "tujhe bhula diya"],
    "party":    ["badri ki dulhania", "kala chashma", "kar gayi chull", "sheila ki jawani", "lungi dance"],
    "gym":      ["believer imagine dragons", "remember the name", "unstoppable sia", "zinda bhaag", "till i collapse"],
    "lofi":     ["lo fi hindi chill", "tum se hi lofi", "kun faya kun lofi", "aaoge jab tum lofi", "baarishein lofi"],
    "romantic": ["kesariya", "tum hi ho", "raatan lambiyan", "pehle bhi main", "hawayein"],
    "devotional": ["hanuman chalisa", "om namah shivaya", "gayatri mantra", "jai mata di", "achyutam keshavam"],
    "90s":      ["kuch kuch hota hai", "tujhe dekha to", "pehla nasha", "ek ladki ko dekha", "ye kaali kaali aankhen"],
}

def analyze_vibe_prompt(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["sad", "dard", "rona", "broken", "cry", "dukh", "udaas"]):
        return random.choice(AI_MOOD_DATABASE["sad"])
    if any(w in p for w in ["party", "dance", "nacho", "club", "dj", "dhoom"]):
        return random.choice(AI_MOOD_DATABASE["party"])
    if any(w in p for w in ["gym", "workout", "energy", "power", "hard", "motivation"]):
        return random.choice(AI_MOOD_DATABASE["gym"])
    if any(w in p for w in ["lofi", "chill", "relax", "sleep", "study", "peaceful"]):
        return random.choice(AI_MOOD_DATABASE["lofi"])
    if any(w in p for w in ["romantic", "love", "pyar", "ishq", "mohabbat"]):
        return random.choice(AI_MOOD_DATABASE["romantic"])
    if any(w in p for w in ["bhajan", "devotional", "mantra", "god", "pooja", "prayer"]):
        return random.choice(AI_MOOD_DATABASE["devotional"])
    if any(w in p for w in ["90s", "old", "classic", "purana", "retro"]):
        return random.choice(AI_MOOD_DATABASE["90s"])
    all_tracks = [t for sub in AI_MOOD_DATABASE.values() for t in sub]
    return random.choice(all_tracks)

# ==============================================================================
# YouTube Engine — ULTIMATE FIX
# ==============================================================================
COOKIES_PATH: Optional[str] = None

def _find_cookies() -> Optional[str]:
    global COOKIES_PATH
    paths = [
        "cookies.txt",
        "/app/cookies.txt",
        os.path.join(os.path.dirname(__file__), "cookies.txt"),
    ]
    for p in paths:
        if os.path.exists(p):
            logger.info(f"✅ cookies.txt found: {p}")
            COOKIES_PATH = p
            return p
    logger.warning("⚠️ cookies.txt NOT found — YouTube may block requests!")
    return None

# Find cookies at startup
_find_cookies()


class YoutubeEngine:

    # Multiple user agents to rotate
    _USER_AGENTS = [
        "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X)",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/114.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    ]

    @classmethod
    def _build_opts(cls) -> dict:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 5,
            "fragment_retries": 5,
            "skip_unavailable_fragments": True,
            "ignoreerrors": False,
            "extract_flat": False,
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android", "web"],
                    "player_skip": [],
                }
            },
            "http_headers": {
                "User-Agent": random.choice(cls._USER_AGENTS),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
                "Referer": "https://www.youtube.com/",
            },
        }
        # Inject cookies if available
        if COOKIES_PATH:
            opts["cookiefile"] = COOKIES_PATH
        return opts

    @staticmethod
    def _extract(query: str) -> Optional[dict]:
        opts = YoutubeEngine._build_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if not info:
                    return None
                # Handle search results
                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        return None
                    info = entries[0]
                # Validate URL exists
                if not info.get("url"):
                    logger.warning("YT: URL missing in extracted info")
                    return None
                return info
        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "Sign in" in err or "bot" in err.lower():
                logger.error("❌ YT Bot detection! Update cookies.txt")
            elif "unavailable" in err.lower():
                logger.error("❌ YT Video unavailable")
            else:
                logger.error(f"❌ YT DownloadError: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ YT Engine crash: {e}")
            return None

    @classmethod
    async def get_track(cls, query: str) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query)
        if not info:
            return None
        # Clean duration
        try:
            duration = int(info.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        # Get best thumbnail
        thumb = DEFAULT_THUMB
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            # Get highest resolution thumbnail
            best = max(
                thumbnails,
                key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                default=None,
            )
            if best and best.get("url"):
                thumb = best["url"]
        elif info.get("thumbnail"):
            thumb = info["thumbnail"]

        return Track(
            id_=info.get("id", "yt_unknown"),
            title=(info.get("title") or "Unknown Track")[:50],
            artist=(info.get("uploader") or info.get("channel") or "YouTube")[:35],
            album="YouTube HQ Stream",
            duration=duration,
            url=info["url"],
            thumb=thumb,
        )


# ==============================================================================
# Smart Track Resolver — YT First, Saavn Fallback
# ==============================================================================
async def resolve_track(query: str, force_yt: bool = False) -> Optional[Track]:
    """
    Always tries YouTube first.
    Falls back to JioSaavn only for search queries (not URLs).
    """
    is_url = any(x in query for x in ["youtube.com", "youtu.be", "https://", "http://"])

    # YouTube — PRIMARY
    logger.info(f"🎯 YT fetch: {query[:60]}")
    track = await YoutubeEngine.get_track(query)
    if track:
        logger.info(f"✅ YT resolved: {track.title}")
        return track

    # Saavn — FALLBACK (only for non-URL searches)
    if not is_url and not force_yt:
        logger.info(f"🔄 YT failed → trying Saavn: {query[:60]}")
        try:
            track = await saavn.get_first_result(query)
            if track:
                logger.info(f"✅ Saavn resolved: {track.title}")
                return track
        except Exception as e:
            logger.warning(f"Saavn error: {e}")

    logger.error(f"❌ All sources failed: {query[:60]}")
    return None


# ==============================================================================
# UI Helpers
# ==============================================================================
def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Anonymous"
    return user.first_name or (f"@{user.username}" if user.username else "User")


def _source_badge(track: Track) -> str:
    if "YouTube" in (track.album or ""):
        return "🎬 YouTube HQ"
    return "🎵 JioSaavn"


def quantum_ui_card(
    track: Track,
    requested_by: str,
    state: ChatState,
    chat_id: int,
) -> str:
    loop_status = "🔁 ON" if state.loop else "❌ OFF"
    dsp = DSP_MATRIX.get(chat_id, "🌌 Pure Linear [HQ]")
    dur = track.duration_str if hasattr(track, "duration_str") else f"{track.duration}s"
    source = _source_badge(track)
    queue_len = len(state.queue)

    return (
        f"<b>🔮 FASTTRACK — NOW PLAYING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎵 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"📀 <b>Source:</b> {source}\n"
        f"🎛️ <b>Sound Space:</b> {dsp}\n"
        f"⏱️ <b>Duration:</b> {dur}\n"
        f"📋 <b>Queue:</b> {queue_len} track(s) pending\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Owner:</b> @stillrahul\n"
        f"🎧 <b>Requested by:</b> {requested_by}\n"
        f"🔁 <b>Loop:</b> {loop_status}\n\n"
        f"✨ <i>FastTrack VC Music — Powered by @stillrahul</i>"
    )


def get_quantum_buttons(state: ChatState) -> InlineKeyboardMarkup:
    pp_text = "▶️ Resume" if state.is_paused else "⏸ Pause"
    pp_cb = "q_resume" if state.is_paused else "q_pause"
    loop_text = "🔁 Loop ON" if state.loop else "🔁 Loop OFF"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pp_text, callback_data=pp_cb),
            InlineKeyboardButton("⏭ Skip", callback_data="q_skip"),
        ],
        [
            InlineKeyboardButton(loop_text, callback_data="q_loop"),
            InlineKeyboardButton("🔀 Shuffle", callback_data="q_shuffle"),
        ],
        [
            InlineKeyboardButton("🧬 Sound Space", callback_data="q_dsp"),
            InlineKeyboardButton("📊 Queue", callback_data="q_matrix"),
        ],
        [
            InlineKeyboardButton("🗑️ Remove Track", callback_data="q_remove"),
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
async def _execute_stream(chat_id: int, track: Track):
    await calls.play(
        chat_id,
        MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,
        ),
    )


async def _send_now_playing(chat_id: int, item, state: ChatState):
    """Send now playing card and store message id."""
    caption = quantum_ui_card(item.track, item.requested_by, state, chat_id)
    try:
        msg = await bot.send_photo(
            chat_id,
            photo=item.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=get_quantum_buttons(state),
        )
        NOW_PLAYING_MSG[chat_id] = msg.id
    except Exception as e:
        logger.warning(f"send_now_playing error: {e}")
        try:
            msg = await bot.send_message(
                chat_id,
                caption,
                reply_markup=get_quantum_buttons(state),
            )
            NOW_PLAYING_MSG[chat_id] = msg.id
        except Exception as e2:
            logger.error(f"send_message fallback error: {e2}")


async def _advance_queue(chat_id: int):
    next_item = queues.next(chat_id)
    if next_item is None:
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        NOW_PLAYING_MSG.pop(chat_id, None)
        return

    try:
        await _execute_stream(chat_id, next_item.track)
        state = queues.get(chat_id)
        await _send_now_playing(chat_id, next_item, state)
    except Exception as e:
        logger.warning(f"Advance queue error [{chat_id}]: {e}")
        await asyncio.sleep(1)
        await _advance_queue(chat_id)


@calls.on_update()
async def on_stream_update(_, update):
    name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)
    if name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and chat_id:
        await _advance_queue(chat_id)


# ==============================================================================
# /play Command
# ==============================================================================
@bot.on_message(filters.command(["play", "p"]) & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🎵 <b>Usage:</b>\n"
            "<code>/play [song name]</code>\n"
            "<code>/play [YouTube URL]</code>\n\n"
            "Example: <code>/play Kesariya</code>"
        )

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)

    status = await message.reply_text(
        "⚡ <b>Fetching from YouTube HQ...</b>"
    )

    track = await resolve_track(query)

    if not track:
        return await status.edit_text(
            "❌ <b>Could not fetch track!</b>\n\n"
            "<b>Possible reasons:</b>\n"
            "• YouTube bot detection (update <code>cookies.txt</code>)\n"
            "• Video unavailable in your region\n"
            "• Invalid URL\n\n"
            "Try: <code>/play song name</code> instead of URL"
        )

    added, position = queues.add(chat_id, track, requester)
    if not added:
        return await status.edit_text(
            f"⚠️ <b>Queue is full!</b> ({getattr(config, 'MAX_QUEUE_SIZE', 50)} tracks max)\n"
            "Use /skip or /stop to clear."
        )

    state = queues.get(chat_id)

    if position == 0:
        # Play immediately
        try:
            await _execute_stream(chat_id, track)
            await _send_now_playing(chat_id, state.current, state)
            await status.delete()
        except NoActiveGroupCall:
            queues.clear(chat_id)
            await status.edit_text(
                "❌ <b>No Voice Chat active!</b>\n"
                "Start a Voice Chat in this group first, then use /play."
            )
        except Exception as e:
            queues.clear(chat_id)
            logger.exception(f"Play error: {e}")
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
            f"👤 <b>By:</b> {requester}"
        )


# ==============================================================================
# /aiplay Command
# ==============================================================================
@bot.on_message(filters.command(["aiplay", "ai"]) & filters.group)
async def cmd_ai_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🤖 <b>AI Play Usage:</b>\n"
            "<code>/aiplay [mood description]</code>\n\n"
            "<b>Moods:</b> sad, party, gym, lofi, romantic, devotional, 90s\n"
            "Example: <code>/aiplay sad vibe</code>"
        )

    prompt = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = f"🤖 AI ({display_name(message)})"

    status = await message.reply_text("🧠 <b>Analyzing your mood...</b>")
    await asyncio.sleep(0.8)

    suggested = analyze_vibe_prompt(prompt)
    await status.edit_text(
        f"🎯 <b>AI Detected Mood Match:</b>\n"
        f"<code>{suggested}</code>\n\n"
        f"⚡ <b>Fetching from YouTube HQ...</b>"
    )

    track = await resolve_track(suggested)

    if not track:
        return await status.edit_text(
            "❌ <b>AI could not find a track. Try again!</b>"
        )

    added, position = queues.add(chat_id, track, requester)
    if not added:
        return await status.edit_text("⚠️ <b>Queue is full!</b>")

    state = queues.get(chat_id)

    if position == 0:
        try:
            await _execute_stream(chat_id, track)
            await _send_now_playing(chat_id, state.current, state)
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


# ==============================================================================
# /skip Command
# ==============================================================================
@bot.on_message(filters.command(["skip", "s"]) & filters.group)
async def cmd_skip(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing or not state.current:
        return await message.reply_text("❌ <b>Nothing is playing!</b>")
    state.loop = False
    await message.reply_text("⏭ <b>Skipping...</b>")
    await _advance_queue(chat_id)


# ==============================================================================
# /stop Command
# ==============================================================================
@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def cmd_stop(_, message: Message):
    chat_id = message.chat.id
    queues.clear(chat_id)
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    NOW_PLAYING_MSG.pop(chat_id, None)
    await message.reply_text("🛑 <b>Stream stopped and queue cleared!</b>")


# ==============================================================================
# /pause Command
# ==============================================================================
@bot.on_message(filters.command("pause") & filters.group)
async def cmd_pause(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing or state.is_paused:
        return await message.reply_text("❌ <b>Nothing to pause!</b>")
    await calls.pause_stream(chat_id)
    state.is_paused = True
    await message.reply_text("⏸ <b>Paused!</b>")


# ==============================================================================
# /resume Command
# ==============================================================================
@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_paused:
        return await message.reply_text("❌ <b>Nothing to resume!</b>")
    await calls.resume_stream(chat_id)
    state.is_paused = False
    await message.reply_text("▶️ <b>Resumed!</b>")


# ==============================================================================
# /queue Command
# ==============================================================================
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
            f"   👤 {state.current.requested_by}"
        )
    if state.queue:
        lines.append("\n<b>Up Next:</b>")
        for idx, item in enumerate(state.queue[:10], 1):
            lines.append(f"<b>{idx}.</b> {item.track.title} — {item.requested_by}")
        if len(state.queue) > 10:
            lines.append(f"\n<i>...and {len(state.queue) - 10} more tracks</i>")

    await message.reply_text("\n".join(lines))


# ==============================================================================
# /shuffle Command
# ==============================================================================
@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.queue:
        return await message.reply_text("❌ <b>Queue is empty!</b>")
    queues.shuffle(chat_id)
    await message.reply_text("🔀 <b>Queue shuffled!</b>")


# ==============================================================================
# /remove Command
# ==============================================================================
@bot.on_message(filters.command(["remove", "rm"]) & filters.group)
async def cmd_remove(_, message: Message):
    chat_id = message.chat.id
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage: <code>/remove [position]</code>\nExample: <code>/remove 2</code>"
        )
    try:
        pos = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ <b>Invalid position number!</b>")

    item = queues.remove_at(chat_id, pos)
    if item:
        await message.reply_text(f"🗑️ <b>Removed:</b> {item.track.title}")
    else:
        await message.reply_text(f"❌ <b>No track at position #{pos}</b>")


# ==============================================================================
# /np Command — Now Playing
# ==============================================================================
@bot.on_message(filters.command(["np", "now"]) & filters.group)
async def cmd_now_playing(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.current:
        return await message.reply_text("❌ <b>Nothing is playing!</b>")

    caption = quantum_ui_card(
        state.current.track,
        state.current.requested_by,
        state,
        chat_id,
    )
    try:
        await bot.send_photo(
            chat_id,
            photo=state.current.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=get_quantum_buttons(state),
        )
    except Exception:
        await message.reply_text(caption, reply_markup=get_quantum_buttons(state))


# ==============================================================================
# /help Command
# ==============================================================================
@bot.on_message(filters.command("help") & filters.group)
async def cmd_help(_, message: Message):
    await message.reply_text(
        "<b>🎵 FastTrack VC Music Bot — Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🎬 Playback:</b>\n"
        "/play [song/URL] — Play a track\n"
        "/aiplay [mood] — AI mood-based play\n"
        "/skip — Skip current track\n"
        "/stop — Stop & clear queue\n"
        "/pause — Pause stream\n"
        "/resume — Resume stream\n"
        "/np — Now playing info\n\n"
        "<b>📋 Queue:</b>\n"
        "/queue — View full queue\n"
        "/shuffle — Shuffle queue\n"
        "/remove [pos] — Remove track\n\n"
        "<b>🤖 AI Moods:</b>\n"
        "sad • party • gym • lofi\n"
        "romantic • devotional • 90s\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Owner:</b> @stillrahul\n"
        "✨ <i>FastTrack VC Music System</i>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 Contact Owner", url="https://t.me/stillrahul")
        ]])
    )


# ==============================================================================
# /start Command
# ==============================================================================
@bot.on_message(filters.command("start"))
async def cmd_start(_, message: Message):
    await message.reply_text(
        "<b>⚡ FastTrack VC Music Bot</b>\n\n"
        "Add me to a group and start a Voice Chat!\n\n"
        "Use /help to see all commands.\n\n"
        "👑 <b>Owner:</b> @stillrahul",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 Owner", url="https://t.me/stillrahul"),
            InlineKeyboardButton("📖 Help", callback_data="show_help"),
        ]])
    )


# ==============================================================================
# Callback Query Handler
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^q_|^show_help$"))
async def handle_callbacks(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    action = query.data

    if action == "show_help":
        await query.answer("Use /help in a group!", show_alert=True)
        return

    state = queues.get(chat_id)

    try:
        # ── Pause ──────────────────────────────────────────────
        if action == "q_pause":
            if not state.is_playing or state.is_paused:
                return await query.answer("Nothing to pause!", show_alert=True)
            await calls.pause_stream(chat_id)
            state.is_paused = True
            await query.message.edit_reply_markup(get_quantum_buttons(state))
            await query.answer("⏸ Paused")

        # ── Resume ─────────────────────────────────────────────
        elif action == "q_resume":
            if not state.is_paused:
                return await query.answer("Already playing!", show_alert=True)
            await calls.resume_stream(chat_id)
            state.is_paused = False
            await query.message.edit_reply_markup(get_quantum_buttons(state))
            await query.answer("▶️ Resumed")

        # ── Skip ───────────────────────────────────────────────
        elif action == "q_skip":
            if not state.is_playing or not state.current:
                return await query.answer("Nothing playing!", show_alert=True)
            state.loop = False
            await query.answer("⏭ Skipping...")
            try:
                await query.message.delete()
            except Exception:
                pass
            await _advance_queue(chat_id)

        # ── Loop ───────────────────────────────────────────────
        elif action == "q_loop":
            if not state.is_playing:
                return await query.answer("Nothing playing!", show_alert=True)
            state.loop = not state.loop
            if state.current:
                new_cap = quantum_ui_card(
                    state.current.track,
                    state.current.requested_by,
                    state,
                    chat_id,
                )
                try:
                    await query.message.edit_caption(
                        caption=new_cap,
                        reply_markup=get_quantum_buttons(state),
                    )
                except Exception:
                    pass
            await query.answer(f"🔁 Loop: {'ON' if state.loop else 'OFF'}")

        # ── Shuffle ────────────────────────────────────────────
        elif action == "q_shuffle":
            if not state.queue:
                return await query.answer("Queue is empty!", show_alert=True)
            queues.shuffle(chat_id)
            await query.answer("🔀 Queue Shuffled!")

        # ── DSP / Sound Space ──────────────────────────────────
        elif action == "q_dsp":
            if not state.is_playing:
                return await query.answer("Play a track first!", show_alert=True)
            profiles = [
                "🌌 Pure Linear [HQ]",
                "🔥 Sub-Bass Boost",
                "🛸 8D Hyper Reverb",
                "🎧 Studio Master Mode",
                "🌊 Crystal Clear Treble",
            ]
            current = DSP_MATRIX.get(chat_id, profiles[0])
            next_idx = (profiles.index(current) + 1) % len(profiles) if current in profiles else 0
            DSP_MATRIX[chat_id] = profiles[next_idx]
            if state.current:
                new_cap = quantum_ui_card(
                    state.current.track,
                    state.current.requested_by,
                    state,
                    chat_id,
                )
                try:
                    await query.message.edit_caption(
                        caption=new_cap,
                        reply_markup=get_quantum_buttons(state),
                    )
                except Exception:
                    pass
            await query.answer(f"🎛️ DSP: {profiles[next_idx]}", show_alert=True)

        # ── Queue Matrix ───────────────────────────────────────
        elif action == "q_matrix":
            if not state.current and not state.queue:
                return await query.answer("Queue is empty!", show_alert=True)
            lines = ["🔮 QUEUE\n━━━━━━━━━━━━━━━"]
            if state.current:
                lines.append(f"▶️ {state.current.track.title}")
            for i, item in enumerate(state.queue[:6], 1):
                lines.append(f"{i}. {item.track.title}")
            if len(state.queue) > 6:
                lines.append(f"...+{len(state.queue) - 6} more")
            await query.answer("\n".join(lines), show_alert=True)

        # ── Lyrics ─────────────────────────────────────────────
        elif action == "q_lyrics":
            if not state.current:
                return await query.answer("Nothing playing!", show_alert=True)
            await query.answer("📜 Sending lyrics...")
            await bot.send_message(
                chat_id,
                f"📜 <b>Lyrics:</b> {state.current.track.title}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>♪ Synced lyrics coming soon!</i>\n"
                f"<i>♪ Enjoy the HQ stream by @stillrahul</i>",
            )

        # ── Remove ─────────────────────────────────────────────
        elif action == "q_remove":
            state = queues.get(chat_id)
            if not state.queue:
                return await query.answer("Queue is empty!", show_alert=True)
            removed = queues.remove_at(chat_id, 1)
            if removed:
                await query.answer(f"🗑️ Removed: {removed.track.title}", show_alert=True)
            else:
                await query.answer("Nothing to remove!", show_alert=True)

        # ── Stop ───────────────────────────────────────────────
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
            idle_sec = getattr(config, "AUTO_LEAVE_SECONDS", 180)
            idle_chats = queues.cleanup_idle(idle_sec)
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
# Boot Sequence
# ==============================================================================
async def _boot():
    print("=" * 65)
    print("  ⚡ FastTrack VC Music Bot — Quantum Edition")
    print("  👑 Owner: @stillrahul")
    print("=" * 65)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    asst_me = await assistant.get_me()

    cookies_status = f"✅ {COOKIES_PATH}" if COOKIES_PATH else "⚠️ NOT FOUND"

    print(f"\n🤖 Bot:       @{bot_me.username}")
    print(f"🎵 Assistant: {asst_me.first_name} [{asst_me.id}]")
    print(f"🍪 Cookies:   {cookies_status}")
    print(f"📡 YT:        PRIMARY | Saavn: FALLBACK")
    print(f"\n✅ Ready!\n")

    asyncio.create_task(watchdog())
    await idle()


def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(_boot())
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        async def _cleanup():
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
            loop.run_until_complete(_cleanup())
        except Exception:
            pass


if __name__ == "__main__":
    main()
