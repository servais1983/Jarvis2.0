from __future__ import annotations

from jarvis_cyber.integrations.entra_id import entra_id_connector
from jarvis_cyber.integrations.github import github_connector
from jarvis_cyber.integrations.google_drive import google_drive_connector
from jarvis_cyber.integrations.jira import jira_connector
from jarvis_cyber.integrations.microsoft_defender import microsoft_defender_connector
from jarvis_cyber.integrations.microsoft_sentinel import microsoft_sentinel_connector


class ConnectorContextService:
    """Expose lightweight connector availability context to text chat prompts."""

    def prompt_context(self) -> str:
        statuses = [
            f"- GitHub : {'configuré' if github_connector.configured else 'non configuré'}",
            f"- Google Drive : {'configuré' if google_drive_connector.configured else 'non configuré'}",
            f"- Jira : {'configuré' if jira_connector.configured else 'non configuré'}",
            f"- Microsoft Entra ID : {'configuré' if entra_id_connector.configured else 'non configuré'}",
            f"- Microsoft Defender : {'configuré' if microsoft_defender_connector.configured else 'non configuré'}",
            f"- Microsoft Sentinel : {'configuré' if microsoft_sentinel_connector.configured else 'non configuré'}",
        ]
        return "\n".join(statuses)


connector_context_service = ConnectorContextService()
