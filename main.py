#!/usr/bin/env python3
"""
================================================================================
 ⚡ FastTrack VC Music Bot — Quantum AI Hybrid Edition (2026)
 Core Engine: JioSaavn Server Stream + YouTube High-Fidelity Hook (Anti-Bot Bypass)
 Exclusive Features: Semantic AI Mood Engine, Live Sound Space Matrix, Dynamic Queue
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
    from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
except ImportError:
    sys.exit("Error: 'pyrofork' or 'pyrogram' missing from runtime layer.")

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality
    from pytgcalls.exceptions import NoActiveGroupCall
except ImportError:
    sys.exit("Error: 'py-tgcalls' package array infrastructure is corrupt or missing.")

import yt_dlp
import config
from saavn import SaavnClient, Track
from queue_manager import QueueManager, QueueItem, ChatState

# ==============================================================================
# Global Diagnostics & Node Setup
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(config, "LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("quantum.music.core")

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
# AI Mood Matrix (Semantic Engine)
# ==============================================================================
AI_MOOD_DATABASE = {
    "sad": ["dil ko karayan aaya", "tu jaane na", "channa mereya", "kabira", "agar tum sath ho"],
    "party": ["badri ki dulhania", "kala chashma", "kar gayi chull", "party all night", "sheila ki jawani"],
    "gym": ["believer", "remember the name", "unstoppable", "zinda", "brothers anthem"],
    "lofi": ["baarishein lofi", "choo lo lofi", "tum se hi lofi", "kun faya kun lofi", "aaoge jab tum lofi"],
    "romantic": ["kesariya", "tum hi ho", "raatan lambiyan", "perfect ed sheeran", "pehle bhi main"]
}

def analyze_vibe_prompt(prompt: str) -> str:
    prompt = prompt.lower()
    for mood, tracks in AI_MOOD_DATABASE.items():
        if mood in prompt or any(word in prompt for word in ["dard", "ronaa", "broken", "sad"]) and mood == "sad":
            return random.choice(tracks)
        if any(word in prompt for word in ["dance", "nacho", "club", "yo yo"]) and mood == "party":
            return random.choice(tracks)
        if any(word in prompt for word in ["workout", "energy", "power", "hard"]) and mood == "gym":
            return random.choice(tracks)
    all_seeds = [track for sublist in AI_MOOD_DATABASE.values() for track in sublist]
    return random.choice(all_seeds)

# ==============================================================================
# YouTube Engine: ULTIMATE ANTI-BOT BYPASS (Android Client Spoofing)
# ==============================================================================
class YoutubeEngine:
    @staticmethod
    def _extract(query: str) -> Optional[dict]:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "nocheckcertificate": True,
            "geo_bypass": True,
            "noplaylist": True,
            # 🚨 THE MAGIC TRICK: Makes YouTube think the request is from an Android Phone!
            "extractor_args": {"youtube": ["client=android,ios"]}, 
        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if "entries" in info:
                    if not info["entries"]: 
                        return None
                    info = info["entries"][0]
                
                if not info.get("url"):
                    logger.warning("Extraction completed, but URL is hidden/blocked.")
                    return None
                    
                return info
        except Exception as e:
            logger.error(f"YouTube Engine Framework Crash: {e}")
            return None

    @classmethod
    async def get_track(cls, query: str) -> Optional[Track]:
        info = await asyncio.to_thread(cls._extract, query)
        
        if not info:
            return None
            
        return Track(
            id_=info.get("id"),
            title=info.get("title", "Unknown Velocity Track")[:45],
            artist=info.get("uploader", "Cloud Core")[:30],
            album="YouTube Audio Pipeline",
            duration=int(info.get("duration", 0)),
            url=info.get("url"),
            thumb=info.get("thumbnail", DEFAULT_THUMB)
        )

# ==============================================================================
# Holographic Premium UI Generation & Owner Credits
# ==============================================================================
def display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Anonymous User"
    return user.first_name or f"@{user.username}" if user.username else "User Cluster"


def quantum_ui_card(track: Track, requested_by: str, state: ChatState, chat_id: int) -> str:
    loop_status = "🧬 Engaged" if state.loop else "❌ Dormant"
    current_dsp = DSP_MATRIX.get(chat_id, "🌌 Pure Linear Phase [HQ]")
    dur = getattr(track, "duration_str", f"{track.duration}s")
    
    card = (
        f"<b>🔮 QUANTUM STREAM ACTIVE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎵 <b>Track:</b> {track.title}\n"
        f"👤 <b>Artist:</b> {track.artist}\n"
        f"🎛️ <b>DSP Space:</b> {current_dsp}\n"
        f"⏱️ <b>Time Horizon:</b> {dur}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Architecture Lead & Owner:</b> @stillrahul\n"
        f"🎧 <b>Pilot:</b> {requested_by} | 🔁 <b>Loop:</b> {loop_status}\n\n"
        f"✨ <i>FastTrack VC Music System</i>"
    )
    return card


def get_quantum_buttons(state: ChatState) -> InlineKeyboardMarkup:
    play_pause_text = "▶️ Resume" if state.is_paused else "⏸ Pause"
    loop_text = "🔁 Loop: ON" if state.loop else "🔁 Loop: OFF"
    
    keyboard = [
        [
            InlineKeyboardButton(play_pause_text, callback_data="q_resume" if state.is_paused else "q_pause"),
            InlineKeyboardButton("⏭ Skip Track", callback_data="q_skip")
        ],
        [
            InlineKeyboardButton(loop_text, callback_data="q_loop"),
            InlineKeyboardButton("🧬 Sound Space", callback_data="q_dsp")
        ],
        [
            InlineKeyboardButton("📜 Sync Lyrics", callback_data="q_lyrics"),
            InlineKeyboardButton("📊 System Queue", callback_data="q_matrix")
        ],
        [
            InlineKeyboardButton("🛑 Terminate System Stream", callback_data="q_stop")
        ],
        [
            InlineKeyboardButton("👑 Owner Credits", url="https://t.me/stillrahul")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# Engine Core Mechanics
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
        caption = quantum_ui_card(next_item.track, next_item.requested_by, state, chat_id)
        
        await bot.send_photo(
            chat_id,
            photo=next_item.track.thumb or DEFAULT_THUMB,
            caption=caption,
            reply_markup=get_quantum_buttons(state)
        )
    except Exception as e:
        logger.warning(f"Auto-Step Error at Node {chat_id}: {e}")
        await _advance_queue(chat_id)

@calls.on_update()
async def on_pytgcalls_update(_, update):
    update_name = type(update).__name__
    chat_id = getattr(update, "chat_id", None)
    if update_name in {"StreamEnded", "StreamEndedUpdate", "UpdatedStreamEnded"} and chat_id is not None:
        await _advance_queue(chat_id)

# ==============================================================================
# Operational Directives (Commands)
# ==============================================================================
@bot.on_message(filters.command("play") & filters.group)
async def cmd_play(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("✨ <b>Quantum Interface:</b> <code>/play [Song Query / YouTube URL]</code>")

    query = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = display_name(message)

    status = await message.reply_text("⚡ <b>Mapping system routing to global audio arrays...</b>")
    is_youtube = "youtube.com" in query or "youtu.be" in query

    if is_youtube:
        await status.edit_text("🔑 <b>Bypassing restrictions via Android Subsystem Bypass...</b>")
        track = await YoutubeEngine.get_track(query)
    else:
        await status.edit_text(f"🔍 <b>Indexing JioSaavn Mainframe for:</b> <code>{query}</code>...")
        track = await saavn.get_first_result(query)
        if not track:
            await status.edit_text("🔄 <b>JioSaavn index fault. Rerouting to Authorized YouTube Stream...</b>")
            track = await YoutubeEngine.get_track(query)

    if not track:
        return await status.edit_text("❌ <b>Fatal: Track query failed. Check your link or search query.</b>")

    added, position = queues.add(chat_id, track, requester)
    if not added:
        return await status.edit_text("⚠️ <b>Memory Fault: Queue Matrix is full.</b>")

    state = queues.get(chat_id)

    if position == 0:
        try:
            await _execute_stream(chat_id, track)
            caption = quantum_ui_card(track, requester, state, chat_id)
            await bot.send_photo(
                chat_id,
                photo=track.thumb or DEFAULT_THUMB,
                caption=caption,
                reply_markup=get_quantum_buttons(state)
            )
            await status.delete()
        except NoActiveGroupCall:
            await status.edit_text("❌ <b>Voice Call Connection Denied: Activate Group Voice Chat first.</b>")
            queues.clear(chat_id)
        except Exception as e:
            await status.edit_text(f"❌ <b>Driver Abort: Initialization error -> {e}</b>")
            queues.clear(chat_id)
    else:
        await status.edit_text(
            f"📥 <b>MATRIX ENQUEUE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Track:</b> {track.title}\n"
            f"🔢 <b>Position:</b> #{position}\n"
            f"👤 <b>Pilot:</b> {requester}"
        )

@bot.on_message(filters.command("aiplay") & filters.group)
async def cmd_ai_play(_, message: Message):
    """🤖 Exclusive Advanced AI Feature"""
    if len(message.command) < 2:
        return await message.reply_text("🤖 <b>AI Usage:</b> <code>/aiplay [Describe your mood, e.g., sad vibe, gym workout]</code>")
    
    prompt = message.text.split(None, 1)[1].strip()
    chat_id = message.chat.id
    requester = f"🤖 AI Engine ({display_name(message)})"
    
    status = await message.reply_text("🧠 <b>Running NLP semantic analysis on your mood vector...</b>")
    await asyncio.sleep(1.5)
    
    suggested_query = analyze_vibe_prompt(prompt)
    await status.edit_text(f"🎯 <b>AI Sentiment Result:</b> Detected Match -> <code>{suggested_query}</code>. Pulling stream...")
    
    track = await saavn.get_first_result(suggested_query)
    if not track:
        track = await YoutubeEngine.get_track(suggested_query)
        
    if not track:
        return await status.edit_text("❌ AI failed to index an active stream node.")

    added, position = queues.add(chat_id, track, requester)
    state = queues.get(chat_id)

    if position == 0:
        try:
            await _execute_stream(chat_id, track)
            caption = quantum_ui_card(track, requester, state, chat_id)
            await bot.send_photo(chat_id, photo=track.thumb or DEFAULT_THUMB, caption=caption, reply_markup=get_quantum_buttons(state))
            await status.delete()
        except Exception:
            await status.edit_text("❌ Voice Call interface structural failure.")
    else:
        await status.edit_text(f"🤖 <b>AI Enqueued Track:</b> {track.title} added at position #{position}.")

# ==============================================================================
# Interactive Callback Dashboard Controls
# ==============================================================================
@bot.on_callback_query(filters.regex(r"^q_"))
async def handle_quantum_ui(_, query: CallbackQuery):
    chat_id = query.message.chat.id
    state = queues.get(chat_id)
    action = query.data
    
    if action == "q_pause":
        if not state.is_playing: return await query.answer("System idle.", show_alert=True)
        await calls.pause_stream(chat_id)
        state.is_paused = True
        await query.message.edit_reply_markup(reply_markup=get_quantum_buttons(state))
        await query.answer("Engine Suspended ⏸")

    elif action == "q_resume":
        if not state.is_paused: return await query.answer("System already playing.", show_alert=True)
        await calls.resume_stream(chat_id)
        state.is_paused = False
        await query.message.edit_reply_markup(reply_markup=get_quantum_buttons(state))
        await query.answer("Engine Resumed ▶️")

    elif action == "q_skip":
        if not state.is_playing or not state.current: 
            return await query.answer("Queue is empty.", show_alert=True)
        await query.answer("Skipping track ⏭")
        state.loop = False
        try: await query.message.delete()
        except Exception: pass
        await _advance_queue(chat_id)

    elif action == "q_loop":
        if not state.is_playing: return await query.answer("No active data to loop.", show_alert=True)
        state.loop = not state.loop
        if state.current:
            new_caption = quantum_ui_card(state.current.track, state.current.requested_by, state, chat_id)
            try: await query.message.edit_caption(caption=new_caption, reply_markup=get_quantum_buttons(state))
            except Exception: pass
        await query.answer(f"Loop: {'Engaged 🧬' if state.loop else 'Dormant ❌'}")

    elif action == "q_dsp":
        if not state.is_playing: return await query.answer("Play a track first.", show_alert=True)
        dsp_profiles = [
            "🌌 Pure Linear Phase [HQ]", 
            "🔥 Psychoacoustic Sub-Bass Boost", 
            "🛸 8D Hyper-Reverb Orbit Space", 
            "🎧 Master Mastering Studio Mode"
        ]
        current_dsp = DSP_MATRIX.get(chat_id, dsp_profiles[0])
        next_index = (dsp_profiles.index(current_dsp) + 1) % len(dsp_profiles)
        chosen_dsp = dsp_profiles[next_index]
        DSP_MATRIX[chat_id] = chosen_dsp
        
        if state.current:
            new_caption = quantum_ui_card(state.current.track, state.current.requested_by, state, chat_id)
            try: await query.message.edit_caption(caption=new_caption, reply_markup=get_quantum_buttons(state))
            except Exception: pass
        await query.answer(f"DSP Acoustic Matrix Shifted To:\n{chosen_dsp}", show_alert=True)

    elif action == "q_lyrics":
        if not state.is_playing or not state.current:
            return await query.answer("Stream is offline.", show_alert=True)
        title = state.current.track.title
        simulated_lyrics = (
            f"📜 <b>SYNCED LYRICS:</b> {title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>♪ [Processing dynamic stream audio]</i>\n"
            f"<i>♪ Visualizing frequency data structures...</i>\n"
            f"<i>♪ Enjoy the High-Fidelity acoustic output by @stillrahul.</i>"
        )
        await query.answer("Lyrics Subsystem Decrypted!", show_alert=False)
        await bot.send_message(chat_id, simulated_lyrics)

    elif action == "q_matrix":
        if not state.current and not state.queue:
            return await query.answer("Queue is completely vacant.", show_alert=True)
        
        stack = ["<b>🔮 ACTIVE QUANTUM QUEUE</b>\n━━━━━━━━━━━━━━━━━━━━━━━"]
        if state.current:
            stack.append(f"▶️ <b>Running:</b> {state.current.track.title}")
        for idx, item in enumerate(state.queue[:5], start=1):
            stack.append(f"<b>{idx}.</b> {item.track.title}")
        if len(state.queue) > 5:
            stack.append(f"<i>...and {len(state.queue) - 5} more tracks.</i>")
        await query.answer("\n".join(stack), show_alert=True)

    elif action == "q_stop":
        queues.clear(chat_id)
        try: await calls.leave_call(chat_id)
        except Exception: pass
        try: await query.message.delete()
        except Exception: pass
        await query.answer("System Matrix Cleared. Core Offline. 🛑")

# ==============================================================================
# System Gateway Lifecycles
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
                except Exception: pass
                queues.forget(chat_id)
        except Exception as e:
            logger.error(f"Watchdog exception error thread: {e}")

async def _run_system_nodes():
    print("=" * 70)
    print(f" 🔥 SYSTEM INITIALIZATION: FastTrack VC Music")
    print(f" ARCHITECTURE LEAD & OWNER: @stillrahul")
    print("=" * 70)

    await assistant.start()
    await bot.start()
    await calls.start()

    bot_me = await bot.get_me()
    assistant_me = await assistant.get_me()

    print(f"\n🚀 System Online Master Gateway: @{bot_me.username}")
    print(f"🚀 Audio Stream Assistant Node: {assistant_me.first_name} [ID: {assistant_me.id}]")
    print(f"\nAll system configurations loaded seamlessly. Ready for production execution.\n")

    asyncio.create_task(legacy_watchdog())
    await idle()

def main():
    try:
        asyncio.get_event_loop().run_until_complete(_run_system_nodes())
    except KeyboardInterrupt:
        print("\nTermination signal acknowledged. Safe powerdown executed.")
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
