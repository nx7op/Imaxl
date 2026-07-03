#!/usr/bin/env python3
"""
================================================================================
 ⚡ FastTrack VC Music Bot — Quantum AI Hybrid Edition (2026)
 Core Engine: YouTube Primary + JioSaavn Fallback
 Developer & System Architect: @stillrahul
================================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import random
from typing import Optional

try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import (
        Message,
        InlineKeyboardMarkup,
        InlineKeyboardButton,
        CallbackQuery,
    )
except ImportError:
    sys.exit("Error: 'pyrofork' missing.")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("Error: 'py-tgcalls' missing.")

import yt_dlp
import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, QueueItem, ChatState

# ==============================================================================
# Logging Setup
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(config, "LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("quantum.music.core")

# ==============================================================================
# Clients Setup
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
DSP_MATRIX = {}

# ==============================================================================
# AI Mood Matrix
# ==============================================================================
AI_MOOD_DATABASE = {
    "sad": [
        "dil ko karayan aaya",
        "tu jaane na",
        "channa mereya",
        "kabira",
        "agar tum sath ho",
    ],
    "party": [
        "badri ki dulhania",
        "kala chashma",
        "kar gayi chull",
        "party all night",
        "sheila ki jawani",
    ],
    "gym": [
        "believer",
        "remember the name",
        "unstoppable",
        "zinda",
        "brothers anthem",
    ],
    "lofi": [
        "baarishein lofi",
        "choo lo lofi",
        "tum se hi lofi",
        "kun faya kun lofi",
        "aaoge jab tum lofi",
    ],
    "romantic": [
        "kesariya",
        "tum hi ho",
        "raatan lambiyan",
        "perfect ed sheeran",
        "pehle bhi main",
    ],
}


def analyze_vibe_prompt(prompt: str) -> str:
    prompt_lower = prompt.lower()
    if any(w in prompt_lower for w in ["sad", "dard", "rona", "broken", "cry"]):
        return random.choice(AI_MOOD_DATABASE["sad"])
    if any(w in prompt_lower for w in ["party", "dance", "nacho", "club"]):
        return random.choice(AI_MOOD_DATABASE["party"])
    if any(w in prompt_lower for w in ["gym", "workout", "energy", "power", "hard"]):
        return random.choice(AI_MOOD_DATABASE["gym"])
    if any(w in prompt_lower for w in ["lofi", "chill", "relax", "sleep"]):
        return random.choice(AI_MOOD_DATABASE["lofi"])
    if any(w in prompt_lower for w in ["romantic", "love", "pyar", "ishq"]):
        return random.choice(AI_MOOD_DATABASE["romantic"])
    all_seeds = [t for sub in AI_MOOD_DATABASE.values() for t in sub]
    return random.choice(all_seeds)


# ==============================================================================
# YouTube Engine — PRIMARY (Cookies + Multi-Client)
# ==============================================================================
class YoutubeEngine:

    @staticmethod
    def _get_cookies_path() -> Optional[str]:
        possible_paths = [
            "cookies.txt",
            "/app/cookies.txt",
            os.path.join(os.path.dirname(__file__), "cookies.txt"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"✅ Cookies loaded: {path}")
                return path
        logger.warning("⚠️ cookies.txt not found! YouTube may block.")
        return None

    @staticmethod
    def _build_opts(cookies_path: Optional[str]) -> dict:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 3,
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android", "web"],
                    "skip": ["hls", "dash"],
                }
            },
            "http_headers": {
                "User-Agent": (
                    "com.google.ios.youtube/19.29.1 "
                    "(iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X)"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
            },
        }
        if cookies_path:
            opts["cookiefile"] = cookies_path
        return opts

    @staticmethod
    def _extract(query: str) -> Optional[dict]:
        cookies_path = YoutubeEngine._get_cookies_path()
        opts = YoutubeEngine._build_opts(cookies_path)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if not info:
                    return None
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        return None
                    info = entries[0]
                if not info.get("url"):
                    logger.warning("URL missing in extracted info.")
                    return None
                return info
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"YT DownloadError: {e}")
            return None
        except Exception as e:
            logger.error(f"YT Engine Crash: {e}")
            return None

    @classmethod
    async def get_track(cls, query: str) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query)
        if not info:
            return None
        return Track(
            id_=info.get("id", "yt_unknown"),
            title=info.get("title", "Unknown Track")[:45],
            artist=info.get("uploader", "YouTube")[:30],
            album="YouTube HQ Stream",
            duration=int(info.get("duration") or 0),
            url=info.get("url"),
            thumb=info.get("thumbnail", DEFAULT_THUMB),
        )


# ==============================================================================
# Smart Play — YT First, Saavn Fallback
# ==============================================================================
async def resolve_track(query: str, is_url: bool = False) -> Optional[Track]:
    """
    Priority:
    1. YouTube (primary — always try first)
    2. JioSaavn (fallback — only if YT fails)
    """
    # Always try YouTube first
    logger.info(f"🎯 Trying YouTube first for: {query}")
    track = await YoutubeEngine.get_track(query)

    if track:
        logger.info(f"✅ YouTube resolved: {track.title}")
        return track

    # Only use Saavn if NOT a direct URL and YT failed
    if not is_url:
        logger.info(f"🔄 YT failed, trying JioSaavn for: {query}")
        try:
            track = await saavn.get_first_result(query)
            if track:
                logger.info(f"✅ Saavn resolved: {track.title}")
                return track
        except Exception as e:
            logger.warning(f"Saavn also failed: {e}")

    logger.error(f"❌ All sources failed for: {query}")
    return None


# ==============================================================================
# UI Generation
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


def quantum_ui_card(
    track: Track,
    requested_by: str,
    state: ChatState,
    chat_id: int,
) -> str:
    loop_status = "🧬 ON" if state.loop else "❌ OFF"
    current_dsp = DSP_MATRIX.get(chat_id, "🌌 Pure Linear Phase [HQ]")
    dur = getattr(track, "duration_str", None) or f"{track.duration}s"
    source = "🎵 YouTube HQ" if "YouTube" in (track.album or "") else "🎶 JioSaavn"

    return (
        f"<b>🔮 QUANTUM STREAM ACTIVE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎵 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"📀 <b>Source:</b> {source}\n"
        f"🎛️ <b>DSP Space:</b> {current_dsp}\n"
        f"⏱️ <b>Duration:</b> {dur}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Owner:</b> @stillrahul\n"
        f"🎧 <b>Requested by:</b> {requested_by} | 🔁 <b>Loop:</b> {loop_status}\n\n"
        f"✨ <i>FastTrack VC Music System</i>"
    )


def get_quantum_buttons(state: ChatState) -> InlineKeyboardMarkup:
    play_pause_text = "▶️ Resume" if state.is_paused else "⏸ Pause"
    cb_play_pause = "q_resume" if state.is_paused else "q_pause"
    loop_text = "🔁 Loop: ON" if state.loop else "🔁 Loop: OFF"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(play_pause_text, callback_data=cb_play_pause),
                InlineKeyboardButton("⏭ Skip", callback_data="q_skip"),
            ],
            [
                InlineKeyboardButton(loop_text, callback_data="q_loop"),
                InlineKeyboardButton("🧬 Sound Space", callback_data="q_dsp"),
            ],
            [
                InlineKeyboardButton("📜 Lyrics", callback_data="q_lyrics"),
                InlineKeyboardButton("📊 Queue", callback_data="q_matrix"),
            ],
            [
                InlineKeyboardButton("🛑 Stop Stream", callback_data="q_stop"),
            ],
            [
                InlineKeyboardButton("👑 Owner", url="https://t.me/stillrahul"),
            ],
        ]
    )


# ==============================================================================
# Stream Engine
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


async def _advance_queue(chat_id: int):
    next_item = queues.next(chat_id)
    if next_item is None:
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        return

    try:
        await _execute_stream(chat_id, next_item.track)
        state = queues.get(chat_id)
        caption = quantum_ui_card(
            next_item.track, next_item.requested_by, state, chat_id
        )
        await bot.send_photo(
            chat_id,
            photo=next_item.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=get_quantum_buttons(state),
        )
    except Exception as e:
        logger.warning(f"Auto-advance error at {chat_id}: {e}")
        await _advance_queue(chat_id)


@calls.on_update()
async def on_pytgcalls_update(_, update):
    update_name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)
    if (
        update_name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"}
        and chat_id is not None
    ):
        await _advance_queue(chat_id)


# ==============================================================================
# Commands
# ==============================================================================
@bot.on_message(filters.command("play") & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "✨ <b>Usage:</b> <code>/play [Song name or YouTube URL]</code>"
        )

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)
    is_url = "youtube.com" in query or "youtu.be" in query

    status = await message.reply_text(
        "⚡ <b>Fetching from YouTube HQ Stream...</b>"
    )

    track = await resolve_track(query, is_url=is_url)

    if not track:
        return await status.edit_text(
            "❌ <b>Failed to fetch track.</b>\n"
            "• Check your YouTube URL\n"
            "• Try a different song name\n"
            "• Cookies might be expired — update <code>cookies.txt</code>"
        )

    added, position = queues.add(chat_id, track, requester)
    if not added:
        return await status.edit_text(
            "⚠️ <b>Queue is full! Skip or stop current track.</b>"
        )

    state = queues.get(chat_id)

    if position == 0:
        try:
            await _execute_stream(chat_id, track)
            caption = quantum_ui_card(track, requester, state, chat_id)
            await bot.send_photo(
                chat_id,
                photo=track.thumb or DEFAULT_THUMB,
                caption=caption,
                reply_markup=get_quantum_buttons(state),
            )
            await status.delete()
        except NoActiveGroupCall:
            await status.edit_text(
                "❌ <b>No active Voice Chat found!</b>\n"
                "Please start a Voice Chat in this group first."
            )
            queues.clear(chat_id)
        except Exception as e:
            logger.exception(f"Stream start error: {e}")
            await status.edit_text(
                f"❌ <b>Stream failed to start:</b>\n<code>{e}</code>"
            )
            queues.clear(chat_id)
    else:
        await status.edit_text(
            f"📥 <b>Added to Queue</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>Track:</b> {track.title}\n"
            f"🔢 <b>Position:</b> #{position}\n"
            f"👤 <b>By:</b> {requester}"
        )


@bot.on_message(filters.command("aiplay") & filters.group)
async def cmd_ai_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "🤖 <b>Usage:</b> <code>/aiplay [mood e.g. sad, gym, party, lofi, romantic]</code>"
        )

    prompt = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = f"🤖 AI ({display_name(message)})"

    status = await message.reply_text(
        "🧠 <b>Analyzing your mood vector...</b>"
    )
    await asyncio.sleep(1)

    suggested_query = analyze_vibe_prompt(prompt)
    await status.edit_text(
        f"🎯 <b>AI Matched:</b> <code>{suggested_query}</code>\n"
        f"⚡ <b>Fetching from YouTube HQ...</b>"
    )

    track = await resolve_track(suggested_query, is_url=False)

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
            caption = quantum_ui_card(track, requester, state, chat_id)
            await bot.send_photo(
                chat_id,
                photo=track.thumb or DEFAULT_THUMB,
                caption=caption,
                reply_markup=get_quantum_buttons(state),
            )
            await status.delete()
        except NoActiveGroupCall:
            await status.edit_text(
                "❌ <b>Start Voice Chat in this group first!</b>"
            )
            queues.clear(chat_id)
        except Exception as e:
            logger.exception(f"AI Stream error: {e}")
            await status.edit_text(f"❌ <b>Stream failed:</b> <code>{e}</code>")
            queues.clear(chat_id)
    else:
        await status.edit_text(
            f"🤖 <b>AI Queued:</b> {track.title} at position #{position}"
        )


# ==============================================================================
# Callback Handlers
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^q_"))
async def handle_quantum_ui(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    state = queues.get(chat_id)
    action = query.data

    try:
        if action == "q_pause":
            if not state.is_playing:
                return await query.answer("Nothing is playing!", show_alert=True)
            await calls.pause_stream(chat_id)
            state.is_paused = True
            await query.message.edit_reply_markup(
                reply_markup=get_quantum_buttons(state)
            )
            await query.answer("⏸ Paused")

        elif action == "q_resume":
            if not state.is_paused:
                return await query.answer("Already playing!", show_alert=True)
            await calls.resume_stream(chat_id)
            state.is_paused = False
            await query.message.edit_reply_markup(
                reply_markup=get_quantum_buttons(state)
            )
            await query.answer("▶️ Resumed")

        elif action == "q_skip":
            if not state.is_playing or not state.current:
                return await query.answer("Queue is empty!", show_alert=True)
            state.loop = False
            await query.answer("⏭ Skipping...")
            try:
                await query.message.delete()
            except Exception:
                pass
            await _advance_queue(chat_id)

        elif action == "q_loop":
            if not state.is_playing:
                return await query.answer("Nothing playing!", show_alert=True)
            state.loop = not state.loop
            if state.current:
                new_caption = quantum_ui_card(
                    state.current.track,
                    state.current.requested_by,
                    state,
                    chat_id,
                )
                try:
                    await query.message.edit_caption(
                        caption=new_caption,
                        reply_markup=get_quantum_buttons(state),
                    )
                except Exception:
                    pass
            await query.answer(
                f"🔁 Loop: {'ON 🧬' if state.loop else 'OFF ❌'}"
            )

        elif action == "q_dsp":
            if not state.is_playing:
                return await query.answer("Play a track first!", show_alert=True)
            dsp_profiles = [
                "🌌 Pure Linear Phase [HQ]",
                "🔥 Psychoacoustic Sub-Bass Boost",
                "🛸 8D Hyper-Reverb Orbit Space",
                "🎧 Master Mastering Studio Mode",
            ]
            current = DSP_MATRIX.get(chat_id, dsp_profiles[0])
            if current in dsp_profiles:
                next_idx = (dsp_profiles.index(current) + 1) % len(dsp_profiles)
            else:
                next_idx = 0
            chosen = dsp_profiles[next_idx]
            DSP_MATRIX[chat_id] = chosen
            if state.current:
                new_caption = quantum_ui_card(
                    state.current.track,
                    state.current.requested_by,
                    state,
                    chat_id,
                )
                try:
                    await query.message.edit_caption(
                        caption=new_caption,
                        reply_markup=get_quantum_buttons(state),
                    )
                except Exception:
                    pass
            await query.answer(f"DSP: {chosen}", show_alert=True)

        elif action == "q_lyrics":
            if not state.is_playing or not state.current:
                return await query.answer("No track playing!", show_alert=True)
            title = state.current.track.title
            await query.answer("📜 Lyrics loading...")
            await bot.send_message(
                chat_id,
                f"📜 <b>LYRICS:</b> {title}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>♪ Enjoy the High-Fidelity stream by @stillrahul</i>",
            )

        elif action == "q_matrix":
            if not state.current and not state.queue:
                return await query.answer("Queue is empty!", show_alert=True)
            lines = ["🔮 ACTIVE QUEUE\n━━━━━━━━━━━━━━━"]
            if state.current:
                lines.append(f"▶️ NOW: {state.current.track.title}")
            for idx, item in enumerate(state.queue[:5], 1):
                lines.append(f"{idx}. {item.track.title}")
            if len(state.queue) > 5:
                lines.append(f"...and {len(state.queue) - 5} more")
            await query.answer("\n".join(lines), show_alert=True)

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
            await query.answer("🛑 Stream stopped!")

    except Exception as e:
        logger.exception(f"Callback error [{action}]: {e}")
        await query.answer("❌ Something went wrong!", show_alert=True)


# ==============================================================================
# Watchdog
# ==============================================================================
async def legacy_watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            auto_leave = getattr(config, "AUTO_LEAVE_SECONDS", 120)
            idle_chats = queues.cleanup_idle(auto_leave)
            for chat_id in idle_chats:
                try:
                    await calls.leave_call(chat_id)
                except Exception:
                    pass
                queues.forget(chat_id)
        except Exception as e:
            logger.error(f"Watchdog error: {e}")


# ==============================================================================
# Boot
# ==============================================================================
async def _run_system_nodes():
    print("=" * 70)
    print(" 🔥 FastTrack VC Music — Quantum Edition")
    print(" OWNER: @stillrahul")
    print("=" * 70)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    assistant_me = await assistant.get_me()

    print(f"\n🚀 Bot: @{bot_me.username}")
    print(f"🎵 Assistant: {assistant_me.first_name} [ID: {assistant_me.id}]")
    print(f"✅ YouTube PRIMARY | JioSaavn FALLBACK")
    print(f"✅ Cookies: {YoutubeEngine._get_cookies_path() or 'NOT FOUND ⚠️'}")
    print(f"\nReady!\n")

    asyncio.create_task(legacy_watchdog())
    await idle()


def main():
    try:
        asyncio.get_event_loop().run_until_complete(_run_system_nodes())
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        async def _cleanup():
            await saavn.close()
            try:
                await bot.stop()
            except Exception:
                pass
            try:
                await assistant.stop()
            except Exception:
                pass
        try:
            asyncio.get_event_loop().run_until_complete(_cleanup())
        except Exception:
            pass


if __name__ == "__main__":
    main()
