"""
queue_manager.py — Per-chat song queue + playback state.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from saavn import Track


@dataclass
class QueueItem:
    track: Track
    requested_by: str


@dataclass
class ChatState:
    queue: list[QueueItem] = field(default_factory=list)
    current: Optional[QueueItem] = None
    is_playing: bool = False
    is_paused: bool = False
    loop: bool = False
    last_activity: float = field(default_factory=time.time)

    def touch(self):
        self.last_activity = time.time()


class QueueManager:
    def __init__(self, max_queue_size: int = 25):
        self.max_queue_size = max_queue_size
        self._chats: dict[int, ChatState] = {}

    def get(self, chat_id: int) -> ChatState:
        if chat_id not in self._chats:
            self._chats[chat_id] = ChatState()
        return self._chats[chat_id]

    def add(self, chat_id: int, track: Track, requested_by: str) -> tuple[bool, int]:
        state = self.get(chat_id)
        state.touch()
        item = QueueItem(track=track, requested_by=requested_by)

        if not state.is_playing and state.current is None:
            state.current = item
            state.is_playing = True
            return True, 0

        if len(state.queue) >= self.max_queue_size:
            return False, -1

        state.queue.append(item)
        return True, len(state.queue)

    def next(self, chat_id: int) -> Optional[QueueItem]:
        state = self.get(chat_id)
        state.touch()

        if state.loop and state.current is not None:
            return state.current

        if state.queue:
            state.current = state.queue.pop(0)
            return state.current

        state.current = None
        state.is_playing = False
        return None

    def skip_list(self, chat_id: int) -> list[QueueItem]:
        return self.get(chat_id).queue

    def clear(self, chat_id: int):
        state = self.get(chat_id)
        state.queue.clear()
        state.current = None
        state.is_playing = False
        state.is_paused = False
        state.loop = False

    def remove_at(self, chat_id: int, index: int) -> Optional[QueueItem]:
        state = self.get(chat_id)
        if 1 <= index <= len(state.queue):
            return state.queue.pop(index - 1)
        return None

    def shuffle(self, chat_id: int):
        import random
        random.shuffle(self.get(chat_id).queue)

    def cleanup_idle(self, idle_seconds: float) -> list[int]:
        now = time.time()
        idle_chats = []
        for chat_id, state in self._chats.items():
            if not state.is_playing and not state.queue:
                if now - state.last_activity > idle_seconds:
                    idle_chats.append(chat_id)
        return idle_chats

    def forget(self, chat_id: int):
        self._chats.pop(chat_id, None)
