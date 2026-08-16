"""Простой fixed-window rate limiter в памяти процесса.

Без внешних зависимостей и без Redis: на проде api — один uvicorn-процесс
(см. Dockerfile CMD без --workers), поэтому счётчик в памяти процесса
корректен. Если когда-нибудь воркеров станет несколько, лимит просто
умножится на их число — приемлемо для защиты публичного эндпоинта от флуда,
а не для точного биллинга.

Считает два измерения в одном окне: число запросов и (опционально) сумму
байт — чтобы снятие лимита на количество вложений не позволяло забить диск.
"""

import threading
import time


class RateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        max_bytes: int | None = None,
        max_entries: int = 10_000,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._lock = threading.Lock()
        # key -> (window_start, request_count, byte_count)
        self._windows: dict[str, tuple[float, int, int]] = {}

    def _purge_locked(self, now: float) -> None:
        """Сбрасываем просроченные окна, чтобы словарь не рос бесконечно."""
        if len(self._windows) <= self.max_entries:
            return
        cutoff = now - self.window_seconds
        stale = [k for k, (start, _, _) in self._windows.items() if start < cutoff]
        for k in stale:
            del self._windows[k]

    def check(self, key: str) -> tuple[bool, int]:
        """Регистрирует запрос и возвращает (разрешён, retry_after_сек).

        Отклоняет, если исчерпан лимит запросов или (когда задан) байтовый
        бюджет окна.
        """
        now = time.monotonic()
        with self._lock:
            start, count, nbytes = self._windows.get(key, (now, 0, 0))
            if now - start >= self.window_seconds:
                start, count, nbytes = now, 0, 0
            retry = max(1, int(self.window_seconds - (now - start)) + 1)
            if count >= self.max_requests:
                return False, retry
            if self.max_bytes is not None and nbytes >= self.max_bytes:
                return False, retry
            self._windows[key] = (start, count + 1, nbytes)
            self._purge_locked(now)
            return True, 0

    def consume_bytes(self, key: str, nbytes: int) -> bool:
        """Добавляет nbytes к байтовому бюджету окна; False — бюджет превышен.

        Вызывается по мере чтения потока загрузки, чтобы отклонить файл,
        который укладывается в per-file лимит, но суммарно переполняет окно.
        """
        if self.max_bytes is None:
            return True
        now = time.monotonic()
        with self._lock:
            start, count, acc = self._windows.get(key, (now, 0, 0))
            if now - start >= self.window_seconds:
                start, count, acc = now, 0, 0
            if acc + nbytes > self.max_bytes:
                return False
            self._windows[key] = (start, count, acc + nbytes)
            return True

    def is_blocked(self, key: str) -> bool:
        """True, если по ключу уже исчерпан лимит в текущем окне — без учёта
        самого вызова (peek). Используется для lockout-схемы входа: сначала
        смотрим «заблокирован ли?», а счётчик увеличиваем только на
        фактической неудаче через record() ниже.
        """
        now = time.monotonic()
        with self._lock:
            start, count, _ = self._windows.get(key, (now, 0, 0))
            if now - start >= self.window_seconds:
                return False
            return count >= self.max_requests

    def record(self, key: str) -> None:
        """Зафиксировать событие (например, неудачную попытку входа) —
        увеличивает счётчик окна, не отклоняя сам вызов.
        """
        now = time.monotonic()
        with self._lock:
            start, count, nbytes = self._windows.get(key, (now, 0, 0))
            if now - start >= self.window_seconds:
                start, count, nbytes = now, 0, 0
            self._windows[key] = (start, count + 1, nbytes)
            self._purge_locked(now)

    def reset(self, key: str) -> None:
        """Сбросить счётчик ключа (успешный вход снимает lockout аккаунта)."""
        with self._lock:
            self._windows.pop(key, None)
