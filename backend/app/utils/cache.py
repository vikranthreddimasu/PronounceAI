"""
Simple in-memory LRU cache for feedback responses.
Cache key: (error_pattern_hash, l1_lang, target_accent).
Replace with Redis when deploying to production.
"""
import hashlib
import json
from cachetools import LRUCache
from threading import Lock

_cache: LRUCache = LRUCache(maxsize=2048)
_lock = Lock()


def _make_key(error_pattern: dict, l1: str, accent: str) -> str:
    payload = json.dumps({"errors": error_pattern, "l1": l1, "accent": accent}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_cached_feedback(error_pattern: dict, l1: str, accent: str) -> list[dict] | None:
    key = _make_key(error_pattern, l1, accent)
    with _lock:
        return _cache.get(key)


def set_cached_feedback(error_pattern: dict, l1: str, accent: str, tips: list[dict]) -> None:
    key = _make_key(error_pattern, l1, accent)
    with _lock:
        _cache[key] = tips


def cache_stats() -> dict:
    with _lock:
        return {"size": len(_cache), "maxsize": _cache.maxsize}
