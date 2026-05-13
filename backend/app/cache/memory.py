"""Thread-safe in-memory LRU cache.

The score router, transcript cache, embedding cache, native-pitch in-memory
cache, and TTS audio cache used to maintain their own near-identical LRU
implementations. This module is the single source.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Generic, Hashable, Optional, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    def __init__(self, max_size: int):
        self.max_size = max(0, max_size)
        self._items: "OrderedDict[K, V]" = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: K) -> Optional[V]:
        if self.max_size <= 0:
            return None
        with self._lock:
            value = self._items.get(key)
            if value is None:
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: K, value: V) -> None:
        if self.max_size <= 0:
            return
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)

    def pop(self, key: K) -> Optional[V]:
        with self._lock:
            return self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._items
