# debouncer.py
from __future__ import annotations
import time
from typing import Any, Dict, Hashable, Tuple

KeyT = Tuple[Hashable, ...] | Hashable

class Debouncer:
    """
    Простая и быстрая утилита антидребезга.
    - хранит последний ключ и время триггера по каждому 'kind'
    - не пускает повтор в течение ttl секунд
    """
    __slots__ = ("ttl", "_last_key", "_last_ts")

    def __init__(self, ttl: float = 0.20) -> None:
        self.ttl = float(ttl)
        self._last_key: Dict[str, KeyT | None] = {}
        self._last_ts: Dict[str, float] = {}

    @staticmethod
    def _now() -> float:
        # быстрые короткие интервалы
        return time.perf_counter()

    def should_fire(self, kind: str, key: KeyT) -> bool:
        # 1) одинаковый ключ подряд — не стреляем
        if self._last_key.get(kind) == key:
            return False
        # 2) слишком рано после прошлого раза — не стреляем
        last = self._last_ts.get(kind, 0.0)
        if (self._now() - last) < self.ttl:
            return False
        # 3) обновляем след (ключ/время) и разрешаем
        now = self._now()
        self._last_key[kind] = key
        self._last_ts[kind] = now
        return True

    # вспомогательные
    def reset_kind(self, kind: str) -> None:
        self._last_key.pop(kind, None)
        self._last_ts.pop(kind, None)

    def reset_all(self) -> None:
        self._last_key.clear()
        self._last_ts.clear()
