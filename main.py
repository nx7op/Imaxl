#!/usr/bin/env python3
"""
================================================================================
 FastTrack VC Music Bot — Premium Luxury Edition
 Streams JioSaavn songs into Telegram Group Voice Chats with Rich UI Panels.
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

import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, QueueItem, ChatState

# ==============================================================================
# Setup & Logging
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("saavn-bot.main")
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pytgcalls").setLevel(logging.WARNING)

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

os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

DEFAULT_THUMB = "https://telegra.ph/file/default_music_thumb.jpg" # Fallback if no album art

# ==============================================================================
# UI Formatting & Component Builders
# ==============================================================================

def premium_caption(track: Track, requested_by: str, state: Optional[ChatState] = None) -> str:
    """Generates a high-end visual card caption for the playing track."""
    loop_status = "✨ Enabled" if (state and state.loop) else "❌ Disabled"
    
    caption = (
        f"<b>🎵 NOW PLAYING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"💿 <b>Album:</b> {track.album or 'Single'}\n"
        f"⏱ <b>Duration:</b> {track.duration_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎧 <b>Requested By:</b> {requested_by}\n"
        f"🔁 <b>Loop Mode:</b> {loop_status}\n"
        f"✨ <i>Powered by {config.BOT_TAGLINE}</i>"
    )
    return caption


def get_control_buttons(state: ChatState) -> InlineKeyboardMarkup:
    """Generates fluid inline control panel grids."""
    play_pause_btn = InlineKeyboardButton("▶️ Resume", callback_data="cb_resume") if state.is_paused else InlineKeyboardButton("⏸ Pause", callback_data="cb_pause")
    loop_btn = InlineKeyboardButton("🔁 Loop: ON", callback_data="cb_loop") if state.loop else InlineKeyboardButton("🔁 Loop: OFF", callback_data="cb_loop")
    
    keyboard = [
        [play_pause_btn, InlineKeyboardButton("⏭ Skip", callback_data="cb_skip")],
        [loop_btn, InlineKeyboardButton("⏹ Stop", callback_data="cb_stop")],
        [InlineKeyboardButton("📜 View Queue", callback_data="cb_queue")]
    ]
    return InlineKeyboardMarkup(keyboard)


def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Anonymous"
    return user.first_name or f"@{user.username}" if user.username else "User"


# ==============================================================================
# Core Core Playback Engines
# ==============================================================================

async def _play_track(chat_id: int, track: Track):
    await calls.play(
        chat_id,
        MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,
        ),
    )


async def _advance_queue(chat_id: int):
    """Automatically steps forward into the queue, delivering visual card updates."""
    next_item = queues.next(chat_id)
    if next_item is None:
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        return

    try:
        await _play_track(chat_id, next_item.track)
        state = queues.get(chat_id)
        
        caption = premium_caption(next_item.track, next_item.requested_by, state)
        buttons = get_control_buttons(state)
        
        await bot.send_photo(
            chat_id,
            photo=next_item.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=buttons
        )
    except Exception as e:
        logger.warning("Queue step failure in chat %s: %s", chat_id, e)
        await _advance_queue(chat_id)


@calls.on_update()
async def on_pytgcalls_update(_, update):
    update_name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)
    if update_name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and chat_id is not None:
        await _advance_queue(chat_id)


# ==============================================================================
# Telegram Command Handlers
# ==============================================================================

@bot.on_message(filters.command("play") & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        err_msg = await message.reply_text("✨ <b>Usage:</b> <code>/play [song name]</code>")
        await asyncio.sleep(5)
        await err_msg.delete()
        return

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)

    # Clean execution: Nuke the user command input instantly
    try:
        await message.delete()
    except (ChatAdminRequired, MessageDeleteForbidden):
        pass

    status = await bot.send_message(chat_id, f"🔍 <b>Searching for</b> <code>{query}</code>...")
    track = await saavn.get_first_result(query)
    
    if not track:
        await status.edit_text(f"❌ <b>No results found for</b> <code>{query}</code>.")
        await asyncio.sleep(5)
        await status.delete()
        return

    added, position = queues.add(chat_id, track, requester)
    if not added:
        await status.edit_text("⚠️ <b>The server playback queue is currently full.</b>")
        await asyncio.sleep(5)
        await status.delete()
        return

    state = queues.get(chat_id)

    if position == 0:
        # Launching a fresh voice stream
        try:
            await _play_track(chat_id, track)
            caption = premium_caption(track, requester, state)
            buttons = get_control_buttons(state)
            
            await bot.send_photo(
                chat_id,
                photo=track.thumb or DEFAULT_THUMB,
                caption=caption,
                reply_markup=buttons
            )
            await status.delete()
        except NoActiveGroupCall:
            await status.edit_text("❌ <b>Voice chat is inactive. Start a group VC and try again.</b>")
            queues.clear(chat_id)
        except Exception as e:
            logger.exception("Playback connection aborted: %s", e)
            await status.edit_text(f"❌ <b>Connection failed. Ensure the assistant bot is an admin in this group chat.</b>")
            queues.clear(chat_id)
    else:
        # Item successfully queued up
        queue_card = (
            f"📥 <b>ADDED TO QUEUE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 <b>Track:</b> {track.title}\n"
            f"🔢 <b>Position:</b> #{position}\n"
            f"👤 <b>Requested By:</b> {requester}"
        )
        await status.edit_text(queue_card)
        await asyncio.sleep(6)
        await status.delete()


# ==============================================================================
# Interactive Control Panel (Callback Queries)
# ==============================================================================

@bot.on_callback_query(filters.regex(r"^cb_"))
async def handle_playback_controls(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    state = queues.get(chat_id)
    action = query.data
    
    if action == "cb_pause":
        if not state.is_playing:
            return await query.answer("Nothing is playing right now.", show_alert=True)
        try:
            await calls.pause_stream(chat_id)
            state.is_paused = True
            await query.message.edit_reply_markup(reply_markup=get_control_buttons(state))
            await query.answer("Playback Paused ⏸")
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)

    elif action == "cb_resume":
        if not state.is_paused:
            return await query.answer("Playback is already flowing.", show_alert=True)
        try:
            await calls.resume_stream(chat_id)
            state.is_paused = False
            await query.message.edit_reply_markup(reply_markup=get_control_buttons(state))
            await query.answer("Playback Resumed ▶️")
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)

    elif action == "cb_skip":
        if not state.is_playing or not state.current:
            return await query.answer("Queue is completely dry.", show_alert=True)
        
        await query.answer("Skipping Track ⏭")
        state.loop = False
        try:
            await query.message.delete()
        except Exception:
            pass
        await _advance_queue(chat_id)

    elif action == "cb_loop":
        if not state.is_playing:
            return await query.answer("Play a song first to engage loops.", show_alert=True)
        
        state.loop = not state.loop
        await query.message.edit_reply_markup(reply_markup=get_control_buttons(state))
        
        # Fresh caption update to show new loop state smoothly
        if state.current:
            new_caption = premium_caption(state.current.track, state.current.requested_by, state)
            try:
                await query.message.edit_caption(caption=new_caption, reply_markup=get_control_buttons(state))
            except Exception:
                pass
        
        await query.answer(f"Looping {'Activated ✨' if state.loop else 'Deactivated ❌'}")

    elif action == "cb_stop":
        queues.clear(chat_id)
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("Playback Halted. Left VC ⏹")

    elif action == "cb_queue":
        if not state.current and not state.queue:
            return await query.answer("The queue is completely empty.", show_alert=True)
        
        lines = ["<b>🎶 Live Server Queue</b>\n━━━━━━━━━━━━━━━"]
        if state.current:
            lines.append(f"▶️ <b>Now:</b> {state.current.track.title}")
        
        for i, item in enumerate(state.queue[:8], start=1):
            lines.append(f"{i}. {item.track.title}")
            
        if len(state.queue) > 8:
            lines.append(f"<i>...and {len(state.queue) - 8} more tracks loaded.</i>")
            
        await query.answer("\n".join(lines), show_alert=True)


# ==============================================================================
# Legacy Command Interceptors (Cleaned Up)
# ==============================================================================

@bot.on_message(filters.command("vchelp") & filters.group)
async def cmd_help(_, message: Message):
    help_text = (
        f"<b>🎶 PREMIUM AUDIO ENGINE INTERFACE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <code>/play [song name]</code> — Inline UI Stream Launcher\n"
        f"👉 <code>/stop</code> — Purge playback entirely\n"
        f"👉 <code>/queue</code> — Print full playlist logs\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>All active stream tracks can be modulated using the graphic control cards sent by the bot.</i>"
    )
    msg = await message.reply_text(help_text)
    try:
        await message.delete()
    except Exception:
        pass


@bot.on_message(filters.command("stop") & filters.group)
async def cmd_stop_legacy(_, message: Message):
    chat_id = message.chat.id
    queues.clear(chat_id)
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    msg = await message.reply_text("⏹ <b>Playback systems forced offline.</b>")
    try:
        await message.delete()
    except Exception:
        pass
    await asyncio.sleep(4)
    await msg.delete()


@bot.on_message(filters.command("queue") & filters.group)
async def cmd_queue_legacy(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    try:
        await message.delete()
    except Exception:
        pass

    if not state.current and not state.queue:
        msg = await bot.send_message(chat_id, "ℹ️ <b>The music queue is currently empty.</b>")
        await asyncio.sleep(4)
        await msg.delete()
        return

    lines = ["<b>🎶 CURRENT SYSTEM QUEUE</b>\n━━━━━━━━━━━━━━━━━━━━━"]
    if state.current:
        lines.append(f"<b>▶️ Active:</b> {state.current.track.title} <i>(Requested by {state.current.requested_by})</i>")
    
    for i, item in enumerate(state.queue, start=1):
        lines.append(f"<b>{i}.</b> {item.track.title} — <i>{item.requested_by}</i>")

    msg = await bot.send_message(chat_id, "\n".join(lines))
    await asyncio.sleep(15)
    await msg.delete()


@bot.on_message(filters.command("start") & filters.private)
async def cmd_start_private(_, message: Message):
    await message.reply_text(
        f"👋 Welcome to <b>{config.BOT_TAGLINE}</b>.\n\n"
        f"Add me to your group chat as an administrator, start an active voice call, and invoke "
        f"<code>/play [song name]</code> to experience zero-latency premium audio streaming.\n\n"
        f"<b>Developer:</b> {config.OWNER_USERNAME}"
    )


# ==============================================================================
# System Watchdogs & Bootstraps
# ==============================================================================

async def idle_watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            idle_chats = queues.cleanup_idle(config.AUTO_LEAVE_SECONDS)
            for chat_id in idle_chats:
                try:
                    await calls.leave_call(chat_id)
                    logger.info("Purged idle audio feed inside chat session: %s", chat_id)
                except Exception:
                    pass
                queues.forget(chat_id)
        except Exception as e:
            logger.warning("Watchdog pipeline error: %s", e)


async def _run():
    print("=" * 64)
    print(f" {config.BOT_TAGLINE} — Premium Core Activated")
    print(f" Engineering Lead: {config.OWNER_USERNAME}")
    print("=" * 64)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    assistant_me = await assistant.get_me()

    print(f"\n✅ Gateway Node: @{bot_me.username}")
    print(f"✅ Audio Bridge: {assistant_me.first_name} (ID: {assistant_me.id})")
    print(f"\nSystems completely operational.\n")

    asyncio.create_task(idle_watchdog())
    await idle()


def main():
    try:
        asyncio.get_event_loop().run_until_complete(_run())
    except KeyboardInterrupt:
        print("\nSystems powered down safely.")
    finally:
        async def _cleanup():
            await saavn.close()
            try: await bot.stop() 
            except Exception: pass
            try: await assistant.stop() 
            except Exception: pass
        try:
            asyncio.get_event_loop().run_until_complete(_cleanup())
        except Exception:
            pass

if __name__ == "__main__":
    main()
saavn = SaavnClient()
queues = QueueManager(max_queue_size=config.MAX_QUEUE_SIZE)

os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)


# ==============================================================================
# Small helpers
# ==============================================================================

def track_caption(track: Track, requested_by: str, position: Optional[int] = None) -> str:
    lines = [f"🎵 <b>{track.title}</b>", f"👤 {track.artist}"]
    if track.album:
        lines.append(f"💿 {track.album}")
    lines.append(f"⏱ {track.duration_str}")
    if position == 0 or position is None:
        lines.append(f"\n▶️ Now playing • requested by {requested_by}")
    else:
        lines.append(f"\n📥 Queued at #{position} • requested by {requested_by}")
    lines.append(f"\n<i>via {config.BOT_TAGLINE} • {config.OWNER_USERNAME}</i>")
    return "\n".join(lines)


def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "someone"
    return user.first_name or user.username or "someone"


async def _play_track(chat_id: int, track: Track):
    """Actually start streaming a track into the VC (assumes assistant is joinable)."""
    await calls.play(
        chat_id,
        MediaStream(
            track.url,
            audio_parameters=AudioQuality.STUDIO,
            video_flags=MediaStream.Flags.IGNORE,  # audio only
        ),
    )


async def _advance_queue(chat_id: int):
    """Called when a track finishes — play the next one, or leave if queue's empty."""
    next_item = queues.next(chat_id)
    if next_item is None:
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        return

    try:
        await _play_track(chat_id, next_item.track)
        await bot.send_message(
            chat_id,
            track_caption(next_item.track, next_item.requested_by, position=0),
        )
    except Exception as e:
        logger.warning("Failed to auto-advance in chat %s: %s", chat_id, e)
        await _advance_queue(chat_id)  # try the one after


# ==============================================================================
# PyTgCalls event: a stream finished playing
# (Modern py-tgcalls 2.3.x consolidated call events into on_update();
#  we detect "stream ended" by class name since exact naming can vary
#  slightly between py-tgcalls versions/forks.)
# ==============================================================================

_STREAM_END_TYPE_NAMES = {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"}


@calls.on_update()
async def on_pytgcalls_update(_, update):
    update_name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)

    if update_name in _STREAM_END_TYPE_NAMES and chat_id is not None:
        await _advance_queue(chat_id)
    else:
        # Log unrecognized update types once at DEBUG so we can identify the
        # correct class name from Railway logs if auto-advance ever misfires.
        logger.debug("pytgcalls update: %s (chat_id=%s)", update_name, chat_id)


# ==============================================================================
# Bot commands
# ==============================================================================

HELP_TEXT = f"""
🎶 <b>{config.BOT_TAGLINE}</b> — VC Music Commands
<i>Developer: {config.OWNER_USERNAME}</i>

/play &lt;song name&gt; — search &amp; play (queues if busy)
/pause — pause playback
/resume — resume playback
/skip — skip current track
/stop — stop &amp; clear queue, leave VC
/queue — show the queue
/remove &lt;n&gt; — remove item #n from queue
/shuffle — shuffle the queue
/loop — toggle repeat on current track
/nowplaying (or /np) — what's playing now
/vcping — check bot latency
/vchelp — this message

<i>Note: I (the assistant account) must already be a member of this group's voice chat area to join. Add me to the group first.</i>
"""


@bot.on_message(filters.command("vchelp") & filters.group)
async def cmd_help(_, message: Message):
    await message.reply_text(HELP_TEXT)


@bot.on_message(filters.command("vcping"))
async def cmd_ping(_, message: Message):
    start = time.time()
    reply = await message.reply_text("🏓 Pinging...")
    latency = (time.time() - start) * 1000
    await reply.edit_text(
        f"🏓 Pong! <b>{latency:.0f} ms</b>\n<i>{config.BOT_TAGLINE} • {config.OWNER_USERNAME}</i>"
    )


@bot.on_message(filters.command("play") & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: <code>/play song name</code>")
        return

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)

    status = await message.reply_text(f"🔎 Searching for <b>{query}</b>...")

    track = await saavn.get_first_result(query)
    if not track:
        await status.edit_text(f"😕 No results found for <b>{query}</b>.")
        return

    added, position = queues.add(chat_id, track, requester)
    if not added:
        await status.edit_text("⚠️ Queue is full. Try again after some songs finish.")
        return

    if position == 0:
        # This is the first track — actually need to start playing it
        try:
            await _play_track(chat_id, track)
        except NoActiveGroupCall:
            await status.edit_text(
                "❌ No active voice chat in this group. Start a voice chat first, then try /play again."
            )
            queues.clear(chat_id)
            return
        except Exception as e:
            logger.exception("Failed to start playback in %s: %s", chat_id, e)
            await status.edit_text(
                f"❌ Couldn't join the voice chat. Make sure {config.OWNER_USERNAME}'s assistant "
                f"account is a member of this group and a voice chat is active.\n\nDetails: {e}"
            )
            queues.clear(chat_id)
            return

    await status.edit_text(track_caption(track, requester, position))


@bot.on_message(filters.command("pause") & filters.group)
async def cmd_pause(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing:
        await message.reply_text("Nothing is playing right now.")
        return
    try:
        await calls.pause_stream(chat_id)
        state.is_paused = True
        await message.reply_text("⏸ Paused.")
    except Exception as e:
        await message.reply_text(f"Couldn't pause: {e}")


@bot.on_message(filters.command("resume") & filters.group)
async def cmd_resume(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_paused:
        await message.reply_text("Playback isn't paused.")
        return
    try:
        await calls.resume_stream(chat_id)
        state.is_paused = False
        await message.reply_text("▶️ Resumed.")
    except Exception as e:
        await message.reply_text(f"Couldn't resume: {e}")


@bot.on_message(filters.command("skip") & filters.group)
async def cmd_skip(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)
    if not state.is_playing or not state.current:
        await message.reply_text("Nothing is playing right now.")
        return

    await message.reply_text("⏭ Skipping...")
    # Force loop off for the track being skipped so _advance_queue doesn't replay it
    state.loop = False
    await _advance_queue(chat_id)


@bot.on_message(filters.command("stop") & filters.group)
async def cmd_stop(_, message: Message):
    chat_id = message.chat.id
    queues.clear(chat_id)
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    await message.reply_text("⏹ Stopped and left the voice chat.")


@bot.on_message(filters.command("queue") & filters.group)
async def cmd_queue(_, message: Message):
    chat_id = message.chat.id
    state = queues.get(chat_id)

    if not state.current and not state.queue:
        await message.reply_text("Queue is empty. Use /play to add a song.")
        return

    lines = ["🎶 <b>Current Queue</b>\n"]
    if state.current:
        lines.append(f"▶️ <b>{state.current.track.title}</b> — {state.current.track.artist}  <i>(now playing)</i>")
    for i, item in enumerate(state.queue, start=1):
        lines.append(f"{i}. {item.track.title} — {item.track.artist}")

    if state.loop:
        lines.append("\n🔁 Loop is ON for the current track.")

    await message.reply_text("\n".join(lines))


@bot.on_message(filters.command("remove") & filters.group)
async def cmd_remove(_, message: Message):
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply_text("Usage: <code>/remove 2</code>")
        return
    idx = int(message.command[1])
    removed = queues.remove_at(message.chat.id, idx)
    if removed:
        await message.reply_text(f"🗑 Removed: <b>{removed.track.title}</b>")
    else:
        await message.reply_text("No such item in the queue.")


@bot.on_message(filters.command("shuffle") & filters.group)
async def cmd_shuffle(_, message: Message):
    queues.shuffle(message.chat.id)
    await message.reply_text("🔀 Queue shuffled.")


@bot.on_message(filters.command("loop") & filters.group)
async def cmd_loop(_, message: Message):
    state = queues.get(message.chat.id)
    state.loop = not state.loop
    await message.reply_text(f"🔁 Loop is now {'ON' if state.loop else 'OFF'}.")


@bot.on_message(filters.command(["nowplaying", "np"]) & filters.group)
async def cmd_nowplaying(_, message: Message):
    state = queues.get(message.chat.id)
    if not state.current:
        await message.reply_text("Nothing is playing right now.")
        return
    await message.reply_text(track_caption(state.current.track, state.current.requested_by, position=0))


@bot.on_message(filters.command("start") & filters.private)
async def cmd_start_private(_, message: Message):
    await message.reply_text(
        f"👋 Hi! I'm <b>{config.BOT_TAGLINE}</b>.\n\n"
        f"Add me to a group, start a voice chat, then use <code>/play song name</code> there.\n\n"
        f"Developer: {config.OWNER_USERNAME}\n\nUse /vchelp in a group to see all commands."
    )


# ==============================================================================
# Background: leave idle voice chats after AUTO_LEAVE_SECONDS
# ==============================================================================

async def idle_watchdog():
    while True:
        await asyncio.sleep(30)
        try:
            idle_chats = queues.cleanup_idle(config.AUTO_LEAVE_SECONDS)
            for chat_id in idle_chats:
                try:
                    await calls.leave_call(chat_id)
                    logger.info("Left idle voice chat in %s (no activity for %ds)", chat_id, config.AUTO_LEAVE_SECONDS)
                except Exception:
                    pass
                queues.forget(chat_id)
        except Exception as e:
            logger.warning("Idle watchdog error: %s", e)


# ==============================================================================
# Entrypoint
# ==============================================================================

async def _run():
    print("=" * 64)
    print(f" {config.BOT_TAGLINE} — starting")
    print(f" Developer: {config.OWNER_USERNAME}")
    print(f" Host: {'Railway' if config.IS_RAILWAY else 'Local'}")
    print("=" * 64)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    assistant_me = await assistant.get_me()

    print(f"\n✅ Bot:       @{bot_me.username}")
    print(f"✅ Assistant: {assistant_me.first_name} (id: {assistant_me.id})")
    print(f"\nAdd the assistant account to any group you want music in,")
    print(f"start a voice chat there, then use /play in that group.\n")

    logger.info(
        "%s is live. Bot=@%s Assistant=%s Dev=%s",
        config.BOT_TAGLINE, bot_me.username, assistant_me.first_name, config.OWNER_USERNAME,
    )

    asyncio.create_task(idle_watchdog())

    await idle()


def main():
    try:
        asyncio.get_event_loop().run_until_complete(_run())
    except KeyboardInterrupt:
        print("\nStopped.")
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
