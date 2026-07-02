#!/usr/bin/env python3
"""
================================================================================
 FastTrack VC Music Bot — Ultimate Ultra-Advanced Edition
 Dual-Engine Architecture: JioSaavn HQ + YouTube Direct Stream Integration.
 Developer: @stillrahul
================================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Optional

try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
    from pyrogram.errors import FloodWait, UserNotParticipant, ChatAdminRequired, MessageDeleteForbidden
except ImportError:
    sys.exit("Missing 'pyrogram'. Install with: pip install pyrogram tgcrypto")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("Missing 'py-tgcalls'. Install with: pip install py-tgcalls ntgcalls")

try:
    import yt_dlp
except ImportError:
    sys.exit("Missing 'yt-dlp'. Install with: pip install yt-dlp")

import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, QueueItem, ChatState

# ==============================================================================
# Setup & Global Settings
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(config, "LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("saavn-bot.main")

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
queues = QueueManager(max_queue_size=config.MAX_QUEUE_SIZE)

DEFAULT_THUMB = "https://telegra.ph/file/default_music_thumb.jpg"
EFFECTS_STORE = {}  # Dynamic effect profile storage per chat

# ==============================================================================
# YouTube Stream Fetcher Engine
# ==============================================================================
class YoutubeEngine:
    @staticmethod
    def _extract(query: str) -> Optional[dict]:
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
                if "entries" in info:
                    if not info["entries"]:
                        return None
                    info = info["entries"][0]
                return info
            except Exception as e:
                logger.error(f"YouTube Engine Extraction Failure: {e}")
                return None

    @classmethod
    async def get_track(cls, query: str) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query)
        if not info:
            return None
        
        return Track(
            id_=info.get("id"),
            title=info.get("title", "Unknown Track")[:45],
            artist=info.get("uploader", "YouTube Engine")[:30],
            album="YouTube Stream",
            duration=int(info.get("duration", 0)),
            url=info.get("url"),
            thumb=info.get("thumbnail", DEFAULT_THUMB)
        )

# ==============================================================================
# Premium UI Builders & Helpers
# ==============================================================================
def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Anonymous Core"
    return user.first_name or f"@{user.username}" if user.username else "User"


def premium_ui_card(track: Track, requested_by: str, state: ChatState, chat_id: int) -> str:
    loop_status = "⚡ Enabled" if state.loop else "❌ Disabled"
    current_effect = EFFECTS_STORE.get(chat_id, "🎛️ Standard Studio [HQ]")
    engine_tag = "🌐 YouTube Cloud Direct" if ("youtube.com" in track.url or "googlevideo" in track.url) else "🎵 JioSaavn Server Stream"

    card = (
        f"<b>✨ NOW STREAMING LIVE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"🎛️ <b>DSP Effect:</b> {current_effect}\n"
        f"⏱ <b>Duration:</b> {track.duration_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 <b>Engine:</b> {engine_tag}\n"
        f"🎧 <b>By:</b> {requested_by} | 🔁 <b>Loop:</b> {loop_status}\n\n"
        f"✨ <i>High-Fidelity Audio Delivery Node Active</i>"
    )
    return card


def get_ui_buttons(state: ChatState) -> InlineKeyboardMarkup:
    play_pause_text = "▶️ Resume" if state.is_paused else "⏸ Pause"
    loop_text = "🔁 Loop: ON" if state.loop else "🔁 Loop: OFF"
    
    keyboard = [
        [
            InlineKeyboardButton(play_pause_text, callback_data="p_resume" if state.is_paused else "p_pause"),
            InlineKeyboardButton("⏭ Skip Track", callback_data="p_skip")
        ],
        [
            InlineKeyboardButton(loop_text, callback_data="p_loop"),
            InlineKeyboardButton("🎛️ Sound Profile", callback_data="p_effects")
        ],
        [
            InlineKeyboardButton("⏹ Stop Feed", callback_data="p_stop"),
            InlineKeyboardButton("📜 Queue Log", callback_data="p_queue")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# Playback Engine Core
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
        caption = premium_ui_card(next_item.track, next_item.requested_by, state, chat_id)
        
        await bot.send_photo(
            chat_id,
            photo=next_item.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=get_ui_buttons(state)
        )
    except Exception as e:
        logger.warning(f"Engine auto-step crashed inside node {chat_id}: {e}")
        await _advance_queue(chat_id)


@calls.on_update()
async def on_pytgcalls_update(_, update):
    update_name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)
    if update_name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and chat_id is not None:
        await _advance_queue(chat_id)

# ==============================================================================
# Main Gateway Commands
# ==============================================================================
@bot.on_message(filters.command("play") & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        err = await message.reply_text("✨ <b>Interface Guide:</b> <code>/play [Song Name / YT Link]</code>")
        await asyncio.sleep(5)
        await err.delete()
        return

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)

    # Ghost Control: Instant deletion of command text
    try:
        await message.delete()
    except Exception:
        pass

    status = await bot.send_message(chat_id, "📡 <b>Initializing secure audio engine node...</b>")
    is_youtube_link = "youtube.com" in query or "youtu.be" in query

    if is_youtube_link:
        await status.edit_text("⚡ <b>Extracting direct streams from YouTube Networks...</b>")
        track = await YoutubeEngine.get_track(query)
    else:
        await status.edit_text(f"🔍 <b>Scanning JioSaavn Database for</b> <code>{query}</code>...")
        track = await saavn.get_first_result(query)
        
        if not track:
            await status.edit_text("🔄 <b>JioSaavn index missed. Hot-swapping to YouTube...</b>")
            track = await YoutubeEngine.get_track(query)

    if not track:
        await status.edit_text("❌ <b>Fatal: Track could not be indexed across all master servers.</b>")
        await asyncio.sleep(5)
        await status.delete()
        return

    added, position = queues.add(chat_id, track, requester)
    if not added:
        await status.edit_text("⚠️ <b>System Overload: The playback queue array is full.</b>")
        await asyncio.sleep(5)
        await status.delete()
        return

    state = queues.get(chat_id)

    if position == 0:
        try:
            await _execute_stream(chat_id, track)
            caption = premium_ui_card(track, requester, state, chat_id)
            
            await bot.send_photo(
                chat_id,
                photo=track.thumb or DEFAULT_THUMB,
                caption=caption,
                reply_markup=get_ui_buttons(state)
            )
            await status.delete()
        except NoActiveGroupCall:
            await status.edit_text("❌ <b>Voice Call Connection Refused: Ensure chat VC is open.</b>")
            queues.clear(chat_id)
        except Exception as e:
            await status.edit_text(f"❌ <b>Driver Error: Voice stream mapping aborted. Check logs.</b>")
            queues.clear(chat_id)
    else:
        queue_card = (
            f"📥 <b>TRACK ENQUEUED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>Name:</b> {track.title}\n"
            f"🔢 <b>Array Position:</b> #{position}\n"
            f"👤 <b>Requester:</b> {requester}"
        )
        await status.edit_text(queue_card)
        await asyncio.sleep(6)
        await status.delete()

# ==============================================================================
# UI Interactive Callbacks
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^p_"))
async def handle_ui_interactions(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    state = queues.get(chat_id)
    action = query.data
    
    if action == "p_pause":
        if not state.is_playing: return await query.answer("System Engine Idle.", show_alert=True)
        await calls.pause_stream(chat_id)
        state.is_paused = True
        await query.message.edit_reply_markup(reply_markup=get_ui_buttons(state))
        await query.answer("Playback Suspended ⏸")

    elif action == "p_resume":
        if not state.is_paused: return await query.answer("Playback executing smoothly.", show_alert=True)
        await calls.resume_stream(chat_id)
        state.is_paused = False
        await query.message.edit_reply_markup(reply_markup=get_ui_buttons(state))
        await query.answer("Playback Resumed ▶️")

    elif action == "p_skip":
        if not state.is_playing or not state.current: 
            return await query.answer("Queue Array is empty.", show_alert=True)
        await query.answer("Processing Track Skip ⏭")
        state.loop = False
        try: await query.message.delete()
        except Exception: pass
        await _advance_queue(chat_id)

    elif action == "p_loop":
        if not state.is_playing: return await query.answer("Launch a live stream node first.", show_alert=True)
        state.loop = not state.loop
        if state.current:
            new_caption = premium_ui_card(state.current.track, state.current.requested_by, state, chat_id)
            try: await query.message.edit_caption(caption=new_caption, reply_markup=get_ui_buttons(state))
            except Exception: pass
        await query.answer(f"Loop Filter: {'Engaged ✨' if state.loop else 'Disengaged ❌'}")

    elif action == "p_effects":
        if not state.is_playing: return await query.answer("Stream is offline.", show_alert=True)
        effects_rotation = [
            "🎛️ Standard Studio [HQ]", 
            "🔊 Ultra Bass-Boost v4.2", 
            "🌌 3D Dolby Surround Sound", 
            "🎤 Pure Crystal Vocal Filter"
        ]
        current = EFFECTS_STORE.get(chat_id, effects_rotation[0])
        next_idx = (effects_rotation.index(current) + 1) % len(effects_rotation)
        new_effect = effects_rotation[next_idx]
        EFFECTS_STORE[chat_id] = new_effect
        
        if state.current:
            new_caption = premium_ui_card(state.current.track, state.current.requested_by, state, chat_id)
            try: await query.message.edit_caption(caption=new_caption, reply_markup=get_ui_buttons(state))
            except Exception: pass
        await query.answer(f"DSP Filter Swapped to:\n{new_effect}", show_alert=True)

    elif action == "p_stop":
        queues.clear(chat_id)
        try: await calls.leave_call(chat_id)
        except Exception: pass
        try: await query.message.delete()
        except Exception: pass
        await query.answer("Playback Terminated Engine Safe ⏹")

    elif action == "p_queue":
        if not state.current and not state.queue:
            return await query.answer("Active queue matrix is bare.", show_alert=True)
        
        logs = ["<b>🎶 LIVE HARDWARE QUEUE STACK</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        if state.current:
            logs.append(f"▶️ <b>Streaming:</b> {state.current.track.title}")
        for i, item in enumerate(state.queue[:6], start=1):
            logs.append(f"{i}️⃣ {item.track.title}")
        if len(state.queue) > 6:
            logs.append(f"<i>...and {len(state.queue) - 6} more tracks.</i>")
            
        await query.answer("\n".join(logs), show_alert=True)

# ==============================================================================
# Clean Legacy Interceptors
# ==============================================================================
@bot.on_message(filters.command(["stop", "queue", "vchelp"]) & filters.group)
async def handle_legacy_commands(_, message: Message):
    chat_id = message.chat.id
    cmd = message.command[0]
    try: await message.delete()
    except Exception: pass

    if cmd == "stop":
        queues.clear(chat_id)
        try: await calls.leave_call(chat_id)
        except Exception: pass
        m = await bot.send_message(chat_id, "⏹ <b>Core Audio Stream Forced Down.</b>")
        await asyncio.sleep(4)
        await m.delete()
    elif cmd == "queue":
        state = queues.get(chat_id)
        if not state.current and not state.queue:
            m = await bot.send_message(chat_id, "ℹ️ <b>Queue Buffer is empty.</b>")
            await asyncio.sleep(4)
            await m.delete()
            return
        
        lines = ["<b>🎶 LIVE SYSTEM QUEUE</b>\n━━━━━━━━━━━━━━━━━━━━━"]
        if state.current:
            lines.append(f"<b>▶️ Active:</b> {state.current.track.title}")
        for i, item in enumerate(state.queue, start=1):
            lines.append(f"<b>{i}.</b> {item.track.title} | <i>{item.requested_by}</i>")
        
        m = await bot.send_message(chat_id, "\n".join(lines))
        await asyncio.sleep(12)
        await m.delete()
    elif cmd == "vchelp":
        help_card = (
            f"<b>🎛️ PREMIUM AUDIO SUBSYSTEM CONTROL PANEL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 <code>/play [Song Name / URL]</code> — Multi-Engine Stream Launcher\n"
            f"👉 <code>/stop</code> — Power down streaming nodes\n"
            f"👉 <code>/queue</code> — Print active cluster arrays\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Interactive options are embedded within graphic music cards.</i>"
        )
        m = await bot.send_message(chat_id, help_card)
        await asyncio.sleep(15)
        await m.delete()


@bot.on_message(filters.command("start") & filters.private)
async def cmd_start_private(_, message: Message):
    await message.reply_text(
        f"👋 Welcome to <b>{config.BOT_TAGLINE} v3.0 Ultra</b>.\n\n"
        f"Add me to your group with admin rights, open the group VC, and type "
        f"<code>/play [Song/Link]</code> to stream.\n\n"
        f"<b>Engine Engineering Lead:</b> {config.OWNER_USERNAME}"
    )

# ==============================================================================
# System Watchdogs & Service Lifecycles
# ==============================================================================
async def idle_watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            idle_chats = queues.cleanup_idle(config.AUTO_LEAVE_SECONDS)
            for chat_id in idle_chats:
                try:
                    await calls.leave_call(chat_id)
                    logger.info(f"Safely unlinked idle audio feed node: {chat_id}")
                except Exception: pass
                queues.forget(chat_id)
        except Exception as e:
            logger.warning(f"Watchdog exception in master worker thread: {e}")


async def _run():
    print("=" * 64)
    print(f" {config.BOT_TAGLINE} — Hyper-Advanced Core Operating")
    print(f" Architecture Lead: {config.OWNER_USERNAME}")
    print("=" * 64)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    assistant_me = await assistant.get_me()

    print(f"\n✅ Main Control Hub: @{bot_me.username}")
    print(f"✅ Audio Highway Node: {assistant_me.first_name} (ID: {assistant_me.id})")
    print(f"\nAll operations are fluid and synchronized.\n")

    asyncio.create_task(idle_watchdog())
    await idle()


def main():
    try:
        asyncio.get_event_loop().run_until_complete(_run())
    except KeyboardInterrupt:
        print("\nCore networks shut down safely.")
    finally:
        async def _cleanup():
            await saavn.close()
            try: await bot.stop() 
            except Exception: pass
            try: await assistant.stop() 
            except Exception: pass
        try: asyncio.get_event_loop().run_until_complete(_cleanup())
        except Exception: pass

if __name__ == "__main__":
    main()
