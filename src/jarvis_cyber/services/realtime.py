from __future__ import annotations

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.prompts import SYSTEM_PROMPT
from jarvis_cyber.profile.store import profile_store
from jarvis_cyber.services.tool_catalog import tool_catalog_service


class RealtimeServiceUnavailableError(RuntimeError):
    """Raised when Realtime features are requested without API credentials."""


class RealtimeService:
    """Create short-lived browser credentials for Realtime sessions."""

    endpoint = "https://api.openai.com/v1/realtime/client_secrets"

    async def mint_client_secret(self, user_id: str) -> dict:
        if settings.openai_api_key is None:
            raise RealtimeServiceUnavailableError

        profile_context = profile_store.prompt_context(user_id)

        payload = {
            "session": {
                "type": "realtime",
                "model": settings.realtime_model,
                "instructions": (
                    f"{SYSTEM_PROMPT}\n\n"
                    "Profil de travail de l'utilisateur :\n"
                    f"{profile_context}"
                ),
                "tools": self._tools(),
                "audio": {
                    "output": {
                        "voice": settings.realtime_voice,
                    }
                },
            }
        }
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _tools() -> list[dict]:
        return tool_catalog_service.definitions()


realtime_service = RealtimeService()
