"""WebSocket connection manager.

The fleet simulator broadcasts live drone telemetry here; every connected
dashboard receives it. `main_loop` is captured at startup so background
threads (e.g. the AI agent tools) can schedule broadcasts safely."""
import asyncio
import json
from typing import List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self.main_loop: asyncio.AbstractEventLoop = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        if not self.active:
            return
        msg = json.dumps(data)
        for ws in list(self.active):
            try:
                await ws.send_text(msg)
            except Exception:
                self.disconnect(ws)

    def broadcast_threadsafe(self, data: dict):
        """Fire-and-forget broadcast from a non-asyncio thread."""
        loop = self.main_loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(data), loop)


manager = ConnectionManager()
