import json

import pytest

from jarvis_cyber.services.realtime_sideband import RealtimeSidebandManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


@pytest.mark.anyio
async def test_sideband_handles_tool_call(monkeypatch) -> None:
    manager = RealtimeSidebandManager()
    websocket = FakeWebSocket()
    monkeypatch.setattr(
        manager,
        "_execute_tool",
        lambda name, arguments, user_id: _async_result({"ok": True}),
    )

    await manager._handle_event(
        websocket,
        {
            "type": "response.function_call_arguments.done",
            "call_id": "call_123",
            "name": "search_knowledge",
            "arguments": '{"query":"phishing"}',
        },
        "user-a",
    )

    first = json.loads(websocket.messages[0])
    second = json.loads(websocket.messages[1])
    assert first["item"]["type"] == "function_call_output"
    assert second["type"] == "response.create"


async def _async_result(value: dict) -> dict:
    return value
