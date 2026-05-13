"""Disk cache with atomic writes and optional TTL.

Callers own the cache key construction (so we do not constrain the keying
scheme — sha256 hex, opaque ids, etc.). This module provides path layout,
atomic write via tmp + rename, and TTL-based expiry.

Each logical cache entry can span multiple files. Two helpers cover the common
patterns we use:

  * ``write_bytes`` / ``read_bytes`` for single-file entries (e.g. .npz)
  * ``write_pair`` / ``read_pair`` for two-file entries (e.g. .wav + .json)
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via a same-directory tempfile and rename.

    A concurrent reader will never see a partial file. Same-directory tempfile
    guarantees ``os.replace`` is atomic on POSIX.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


class DiskCache:
    """File-based cache rooted at ``base_dir``."""

    def __init__(self, base_dir: Path | str, ttl_hours: Optional[float] = None):
        self.base_dir = Path(base_dir)
        self.ttl_seconds = ttl_hours * 3600 if ttl_hours else None

    def _ensure(self) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def path(self, key: str, ext: str) -> Path:
        return self._ensure() / f"{key}{ext}"

    def exists(self, key: str, ext: str) -> bool:
        return self.path(key, ext).exists()

    def _expired(self, p: Path) -> bool:
        if self.ttl_seconds is None:
            return False
        try:
            age = time.time() - p.stat().st_mtime
        except OSError:
            return True
        return age > self.ttl_seconds

    def _drop(self, key: str, exts: list[str]) -> None:
        for ext in exts:
            try:
                self.path(key, ext).unlink(missing_ok=True)
            except Exception:
                pass

    # ── single-file ─────────────────────────────────────────────────

    def read_bytes(self, key: str, ext: str) -> Optional[bytes]:
        p = self.path(key, ext)
        if not p.exists():
            return None
        if self._expired(p):
            self._drop(key, [ext])
            return None
        try:
            return p.read_bytes()
        except OSError as e:
            logger.warning("disk_cache: read failed key=%s ext=%s: %s", key[:12], ext, e)
            return None

    def write_bytes(self, key: str, ext: str, data: bytes) -> None:
        write_atomic(self.path(key, ext), data)

    # ── two-file (wav + meta) ───────────────────────────────────────

    def read_pair(self, key: str, ext_a: str, ext_b: str) -> Optional[Tuple[bytes, str]]:
        """Read two associated files. Both must exist + be within TTL."""
        a = self.path(key, ext_a)
        b = self.path(key, ext_b)
        if not (a.exists() and b.exists()):
            return None
        if self._expired(a):
            self._drop(key, [ext_a, ext_b])
            return None
        try:
            return a.read_bytes(), b.read_text()
        except OSError as e:
            logger.warning("disk_cache: read_pair failed key=%s: %s", key[:12], e)
            return None

    def write_pair(
        self,
        key: str,
        ext_a: str,
        data_a: bytes,
        ext_b: str,
        text_b: str,
    ) -> None:
        write_atomic(self.path(key, ext_a), data_a)
        write_atomic(self.path(key, ext_b), text_b.encode("utf-8"))
