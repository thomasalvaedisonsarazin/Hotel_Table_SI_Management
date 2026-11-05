"""Pushes live updates to browsers. Single-process, so run one worker until this moves to Redis."""

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def join(self, restaurant_id: int, socket: WebSocket) -> None:
        self._rooms[restaurant_id].add(socket)

    def leave(self, restaurant_id: int, socket: WebSocket) -> None:
        self._rooms[restaurant_id].discard(socket)

    async def _broadcast(self, restaurant_id: int, message: dict[str, Any]) -> None:
        for socket in list(self._rooms.get(restaurant_id, ())):
            try:
                await socket.send_json(message)
            except Exception:
                logger.info("Dropping closed WebSocket for restaurant %s", restaurant_id)
                self.leave(restaurant_id, socket)

    def publish(self, restaurant_id: int, message: dict[str, Any]) -> None:
        """Safe to call from worker threads, which is where sync endpoints run."""
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(restaurant_id, message), self._loop)


hub = Hub()


def publish_floor_changed(restaurant_id: int) -> None:
    hub.publish(restaurant_id, {"type": "floor_changed"})
