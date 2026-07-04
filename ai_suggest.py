"""
ai_suggest.py — Smart next-song suggestion engine.
Tries an AI suggestion first, falls back to genre/artist-based picks.
Per-chat history aware so multiple groups never mix context.
"""

import asyncio
import logging
import random
import re
from urllib.parse import quote

import httpx

import config

logger = logging.getLogger("fasttrack.ai")

# Per-chat memory: last few tracks played, so suggestions don't repeat
CHAT_HISTORY: dict[int, list[str]] = {}
HISTORY_LIMIT = 8

_client = httpx.AsyncClient(timeout=config.AI_SUGGEST_TIMEOUT)

# Fallback genre pools if AI suggestion fails or repeats
FALLBACK_POOL = {
    "romantic": ["kesariya", "tum hi ho", "raataan lambiyan", "pehle bhi main", "hawayein", "chaleya"],
    "party": ["kala chashma", "kar gayi chull", "lungi dance", "sheila ki jawani", "abhi toh party"],
    "sad": ["tu jaane na", "channa mereya", "kabira", "agar tum sath ho", "tujhe bhula diya"],
    "chill": ["hindi lofi chill", "tum se hi lofi", "baarishein lofi", "aaoge jab tum lofi"],
    "90s": ["pehla nasha", "tujhe dekha to", "kuch kuch hota hai", "ye kaali kaali aankhen"],
    "gym": ["believer", "unstoppable sia", "till i collapse", "zinda"],
}


def _remember(chat_id: int, query: str):
    hist = CHAT_HISTORY.setdefault(chat_id, [])
    hist.append(query.lower())
    if len(hist) > HISTORY_LIMIT:
        hist.pop(0)


def _already_played(chat_id: int, query: str) -> bool:
    hist = CHAT_HISTORY.get(chat_id, [])
    return query.lower() in hist


def _clean_ai_text(text: str) -> str:
    """Strip quotes, numbering, extra explanation from AI response."""
    text = text.strip()
    text = re.sub(r'^["\'\d\.\)\s-]+', "", text)
    text = re.sub(r'["\']+$', "", text)
    # Only take first line — AI sometimes adds extra chatter
    text = text.split("\n")[0].strip()
    return text


async def _ask_ai(last_title: str, last_artist: str) -> str | None:
    prompt = (
        f"Suggest exactly one Bollywood or Hindi song similar in mood to "
        f'"{last_title}" by {last_artist}. '
        f"Reply with ONLY the song name and artist, nothing else, no quotes, no explanation."
    )
    url = f"{config.AI_SUGGEST_BASE}?q={quote(prompt)}"

    try:
        resp = await _client.get(url)
        resp.raise_for_status()
        data = resp.json()
        text = (
            data.get("response")
            or data.get("result")
            or data.get("answer")
            or data.get("text")
        )
        if not text or not isinstance(text, str):
            return None
        cleaned = _clean_ai_text(text)
        if 2 <= len(cleaned) <= 80:
            return cleaned
        return None
    except Exception as e:
        logger.warning(f"AI suggest failed: {str(e)[:100]}")
        return None


def _fallback_pick(chat_id: int, last_album: str = "") -> str:
    pool = random.choice(list(FALLBACK_POOL.values()))
    random.shuffle(pool)
    for song in pool:
        if not _already_played(chat_id, song):
            return song
    return random.choice(pool)


async def suggest_next(chat_id: int, last_title: str, last_artist: str) -> str:
    """
    Main entry point: try AI first, fall back to genre pool.
    Guarantees a non-empty query string is always returned.
    """
    ai_pick = await _ask_ai(last_title, last_artist)
    if ai_pick and not _already_played(chat_id, ai_pick):
        _remember(chat_id, ai_pick)
        return ai_pick

    pick = _fallback_pick(chat_id)
    _remember(chat_id, pick)
    return pick


def forget_chat(chat_id: int):
    CHAT_HISTORY.pop(chat_id, None)


async def close():
    await _client.aclose()
