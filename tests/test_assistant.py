from jarvis_cyber.core.schemas import KnowledgeSearchResult
from jarvis_cyber.services.assistant import AssistantService


def test_build_citations() -> None:
    citations = AssistantService._build_citations(
        [
            KnowledgeSearchResult(
                chunk_id="doc:0",
                document_id="doc",
                title="Playbook phishing",
                source="playbook.md",
                snippet="Vérifier les URLs.",
                score=0.9,
            )
        ]
    )

    assert citations[0].citation_id == "S1"
    assert citations[0].source == "playbook.md"


def test_assistant_uses_inbox_summary(monkeypatch) -> None:
    service = AssistantService()
    service._client = object()
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.memory_store.append",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.memory_store.recent",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.knowledge_store.search",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.knowledge_store.chunks_for_results",
        lambda user_id, results: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.profile_store.prompt_context",
        lambda user_id: "profil",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.playbook_store.prompt_context",
        lambda user_id, message: "playbooks",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.inbox_store.summary_context",
        lambda user_id: "- Brief du matin est prêt (automation_succeeded)",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.connector_context_service.prompt_context",
        lambda: "- GitHub : configuré",
    )

    captured = {}

    class FakeResponses:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return type("Response", (), {"output": [], "output_text": "ok"})()

    service._client = type("Client", (), {"responses": FakeResponses()})()

    service.respond("analyst-1", "session", "Que dois-je regarder ?", role="analyst")

    assert "Inbox non lue" in captured["instructions"]
    assert "Brief du matin est prêt" in captured["instructions"]
    assert "Connecteurs disponibles" in captured["instructions"]
    assert "GitHub : configuré" in captured["instructions"]


def test_assistant_executes_text_chat_tools(monkeypatch) -> None:
    service = AssistantService()
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.memory_store.append",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.memory_store.recent",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.knowledge_store.search",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.knowledge_store.chunks_for_results",
        lambda user_id, results: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.profile_store.prompt_context",
        lambda user_id: "profil",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.playbook_store.prompt_context",
        lambda user_id, message: "playbooks",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.inbox_store.summary_context",
        lambda user_id: "Aucun élément non lu.",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.connector_context_service.prompt_context",
        lambda: "- Jira : configuré",
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.tool_catalog_service.definitions",
        lambda: [{"type": "function", "name": "search_jira_issues"}],
    )
    calls = []
    monkeypatch.setattr(
        "jarvis_cyber.services.assistant.tool_catalog_service.execute",
        lambda name, arguments, user_id, **kwargs: calls.append((name, arguments, user_id, kwargs))
        or {"issues": [{"key": "SEC-1"}]},
    )

    class FakeItem:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    responses = [
        type(
            "Response",
            (),
            {
                "output": [
                    FakeItem(
                        type="function_call",
                        name="search_jira_issues",
                        call_id="call-1",
                        arguments='{"jql":"project = SEC"}',
                    )
                ],
                "output_text": "",
            },
        )(),
        type("Response", (), {"output": [], "output_text": "Ticket SEC-1 trouvé."})(),
    ]

    class FakeResponses:
        @staticmethod
        def create(**kwargs):
            return responses.pop(0)

    service._client = type("Client", (), {"responses": FakeResponses()})()

    answer, *_ = service.respond(
        "analyst-1",
        "session",
        "Quels tickets Jira dois-je regarder ?",
        role="analyst",
    )

    assert answer == "Ticket SEC-1 trouvé."
    assert calls == [
        (
            "search_jira_issues",
            {"jql": "project = SEC"},
            "analyst-1",
            {"role": "analyst", "source": "text_chat"},
        )
    ]
