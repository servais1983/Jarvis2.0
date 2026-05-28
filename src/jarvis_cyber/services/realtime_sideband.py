from __future__ import annotations

import asyncio
import json
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from jarvis_cyber.config import settings
from jarvis_cyber.core.prompts import SYSTEM_PROMPT
from jarvis_cyber.profile.store import profile_store
from jarvis_cyber.services.realtime import RealtimeService, RealtimeServiceUnavailableError
from jarvis_cyber.services.tool_catalog import tool_catalog_service


class RealtimeSidebandManager:
    """Own server-side control channels for in-progress Realtime calls."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._sockets: dict[str, ClientConnection] = {}
        self._user_ids: dict[str, str] = {}

    async def connect(self, call_id: str, user_id: str) -> bool:
        if settings.openai_api_key is None:
            raise RealtimeServiceUnavailableError
        if call_id in self._tasks:
            return True

        self._user_ids[call_id] = user_id
        self._tasks[call_id] = asyncio.create_task(self._run_session(call_id, user_id))
        return True

    async def disconnect(self, call_id: str) -> bool:
        task = self._tasks.pop(call_id, None)
        socket = self._sockets.pop(call_id, None)
        self._user_ids.pop(call_id, None)
        if socket is not None:
            await socket.close()
        if task is not None:
            task.cancel()
        return task is not None or socket is not None

    async def _run_session(self, call_id: str, user_id: str) -> None:
        url = f"wss://api.openai.com/v1/realtime?call_id={call_id}"
        headers = {"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"}

        try:
            async with connect(url, additional_headers=headers) as websocket:
                self._sockets[call_id] = websocket
                profile_context = profile_store.prompt_context(user_id)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "session.update",
                            "session": {
                                "type": "realtime",
                                "instructions": (
                                    f"{SYSTEM_PROMPT}\n\n"
                                    "Profil de travail de l'utilisateur :\n"
                                    f"{profile_context}"
                                ),
                                "tools": RealtimeService._tools(),
                            },
                        }
                    )
                )
                async for message in websocket:
                    await self._handle_event(websocket, json.loads(message), user_id)
        finally:
            self._tasks.pop(call_id, None)
            self._sockets.pop(call_id, None)
            self._user_ids.pop(call_id, None)

    async def _handle_event(self, websocket: Any, payload: dict, user_id: str) -> None:
        if payload.get("type") != "response.function_call_arguments.done":
            return

        call_id = payload["call_id"]
        function_name = payload["name"]
        arguments = json.loads(payload.get("arguments") or "{}")

        try:
            result = await self._execute_tool(function_name, arguments, user_id)
        except Exception:
            result = {"error": "tool_execution_failed"}

        await websocket.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result),
                    },
                }
            )
        )
        await websocket.send(json.dumps({"type": "response.create"}))

    async def _execute_tool(self, name: str, arguments: dict, user_id: str) -> dict:
        return await asyncio.to_thread(
            tool_catalog_service.execute,
            name,
            arguments,
            user_id,
            role=self._role_for_user(user_id),
            source="realtime",
        )

    @staticmethod
    def _role_for_user(user_id: str) -> str:
        if user_id == "local-dev":
            return "admin"
        from jarvis_cyber.auth import auth_service

        for user in auth_service.list_users():
            if user.user_id == user_id:
                return user.role
        return "analyst"


realtime_sideband_manager = RealtimeSidebandManager()
