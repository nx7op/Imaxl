#!/usr/bin/env python3
"""
================================================================================
 FastTrack VC Music Bot — Advanced Edition
 Streams JioSaavn songs directly into Telegram Group Voice Chats.
 Developer: @stillrahul
================================================================================

ARCHITECTURE
------------
Telegram Bot API cannot join voice chats — only a regular user account can.
So this bot runs TWO Telegram clients together:

  1. BOT  (Pyrogram Client, via BOT_TOKEN)
     - What users actually talk to: /play, /skip, /pause, etc.
     - Cannot join VCs itself.

  2. ASSISTANT / userbot (Pyrogram Client, via SESSION_STRING)
     - A real user account that silently joins the group's voice chat
       and streams audio into it, controlled by PyTgCalls.
     - Must already be a MEMBER of any group you want to play music in
       (add it manually, or use /play in a group where it's present —
       see README for adding it).

COMMANDS (all group chats where both accounts are members)
------------------------------------------------------------------------------
  /play <song name>     Search JioSaavn + play (or queue if something's playing)
  /pause                Pause current playback
  /resume                Resume playback
  /skip                  Skip to next track in queue
  /stop                   Stop playback, clear queue, leave VC
  /queue                  Show current queue
  /remove <n>              Remove item #n from the queue
  /shuffle                  Shuffle the queue
  /loop                      Toggle repeat for the current track
  /nowplaying / /np           Show what's currently playing
  /vcping                       Check bot + assistant latency
  /vchelp                        Show this command list

RUNNING LOCALLY
------------------------------------------------------------------------------
    pip install -r requirements.txt
    python3 main.py
(Prompts for missing required env vars in the terminal if not set.)

DEPLOYING ON RAILWAY — see README.md for full step-by-step.
Required Variables: API_ID, API_HASH, BOT_TOKEN, SESSION_STRING
================================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Optional

# ---- Friendly dependency check ----
try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import Message
    from pyrogram.errors import FloodWait, UserNotParticipant, ChatAdminRequired
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
from queue_manager import QueueManager, QueueItem

# ==============================================================================
# Logging
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("saavn-bot.main")
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pytgcalls").setLevel(logging.WARNING)


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
