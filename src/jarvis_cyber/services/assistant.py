import json
from typing import Callable, TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from jarvis_cyber.config import settings
from jarvis_cyber.core.prompts import SYSTEM_PROMPT
from jarvis_cyber.core.schemas import KnowledgeCitation, KnowledgeSearchResult
from jarvis_cyber.knowledge.store import knowledge_store
from jarvis_cyber.inbox.store import inbox_store
from jarvis_cyber.memory.store import memory_store
from jarvis_cyber.playbooks.store import playbook_store
from jarvis_cyber.profile.store import profile_store
from jarvis_cyber.services.connector_context import connector_context_service
from jarvis_cyber.services.tool_catalog import tool_catalog_service


StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)


class AssistantService:
    """Thin orchestration layer for the assistant."""

    max_tool_rounds = 3

    def __init__(self) -> None:
        self._client = (
            OpenAI(api_key=settings.openai_api_key.get_secret_value())
            if settings.openai_api_key
            else None
        )

    def respond(
        self,
        user_id: str,
        session_id: str,
        message: str,
        *,
        role: str = "admin",
    ) -> tuple[str, str, bool, list[KnowledgeSearchResult], list[KnowledgeCitation]]:
        memory_store.append(user_id=user_id, session_id=session_id, role="user", content=message)
        history = memory_store.recent(
            user_id=user_id,
            session_id=session_id,
            limit=settings.history_limit,
        )
        knowledge_hits = knowledge_store.search(
            user_id=user_id,
            query=message,
            limit=settings.knowledge_max_chunks,
        )
        knowledge_chunks = knowledge_store.chunks_for_results(user_id, knowledge_hits)
        citations = self._build_citations(knowledge_hits)
        profile_context = profile_store.prompt_context(user_id)
        playbook_context = playbook_store.prompt_context(user_id, message)
        inbox_context = inbox_store.summary_context(user_id)
        connector_context = connector_context_service.prompt_context()

        if self._client is None:
            answer = self._local_chat_fallback(message, len(knowledge_hits))
            memory_store.append(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=answer,
            )
            return answer, settings.main_model, False, knowledge_hits, citations

        context_block = self._format_knowledge_context(knowledge_chunks)
        instructions = (
            f"{SYSTEM_PROMPT}\n\n"
            "Profil de travail de l'utilisateur :\n"
            f"{profile_context}\n\n"
            "Playbooks personnels pertinents :\n"
            f"{playbook_context}\n\n"
            "Inbox non lue :\n"
            f"{inbox_context}\n\n"
            "Connecteurs disponibles :\n"
            f"{connector_context}\n\n"
            "Contexte documentaire interne disponible :\n"
            f"{context_block}\n\n"
            "Tu disposes d'outils de lecture et de quelques outils d'action. Utilise les outils "
            "de lecture quand la question dépend d'une donnée externe ou d'un état récent que tu "
            "ne peux pas déduire du contexte seul. Pour toute action qui modifie l'état, prépare "
            "la demande mais laisse les garde-fous exiger l'approbation humaine avant exécution.\n\n"
            "Quand tu t'appuies sur le contexte documentaire, cite les sources internes "
            "avec le format [S1], [S2], etc."
        )

        try:
            response = self._respond_with_tools(
                user_id=user_id,
                role=role,
                instructions=instructions,
                history=[{"role": turn.role, "content": turn.content} for turn in history],
            )
        except OpenAIError:
            answer = self._local_chat_fallback(message, len(knowledge_hits))
            memory_store.append(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=answer,
            )
            return answer, settings.main_model, False, knowledge_hits, citations
        answer = response.output_text
        memory_store.append(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=answer,
        )
        return answer, settings.main_model, True, knowledge_hits, citations

    def _respond_with_tools(
        self,
        user_id: str,
        role: str,
        instructions: str,
        history: list[dict],
    ):
        input_items = list(history)
        response = self._client.responses.create(
            model=settings.main_model,
            instructions=instructions,
            tools=tool_catalog_service.definitions(),
            input=input_items,
        )
        for _ in range(self.max_tool_rounds):
            output_items = getattr(response, "output", [])
            tool_calls = [item for item in output_items if item.type == "function_call"]
            if not tool_calls:
                return response

            input_items.extend(output_items)
            input_items.extend(self._tool_outputs(tool_calls, user_id, role))
            response = self._client.responses.create(
                model=settings.main_model,
                instructions=instructions,
                tools=tool_catalog_service.definitions(),
                input=input_items,
            )
        return response

    @staticmethod
    def _tool_outputs(tool_calls: list, user_id: str, role: str) -> list[dict]:
        outputs = []
        for call in tool_calls:
            try:
                arguments = json.loads(call.arguments or "{}")
                result = tool_catalog_service.execute(
                    call.name,
                    arguments,
                    user_id,
                    role=role,
                    source="text_chat",
                )
            except Exception:
                result = {"error": "tool_execution_failed"}
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )
        return outputs

    def complete(self, instructions: str, input_text: str) -> tuple[str, str, bool]:
        if self._client is None:
            return self._local_workflow_fallback(input_text), settings.main_model, False

        response = self._client.responses.create(
            model=settings.main_model,
            instructions=instructions,
            input=input_text,
        )
        return response.output_text, settings.main_model, True

    def complete_structured(
        self,
        instructions: str,
        input_text: str,
        response_model: type[StructuredModelT],
        local_fallback: Callable[[], StructuredModelT],
    ) -> tuple[StructuredModelT, str, bool]:
        if self._client is None:
            return local_fallback(), settings.main_model, False

        response = self._client.responses.parse(
            model=settings.main_model,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            text_format=response_model,
        )
        return response.output_parsed, settings.main_model, True

    @staticmethod
    def _local_workflow_fallback(input_text: str) -> str:
        preview = " ".join(input_text.split())[:180]
        return (
            "Mode local actif : le workflow est prêt mais aucun modèle distant n'est configuré. "
            f"Contenu reçu : {preview}"
        )

    @staticmethod
    def _local_chat_fallback(message: str, knowledge_hit_count: int) -> str:
        return (
            "Jarvis Cyber est prêt en mode local. "
            f"Demande reçue : « {message} ». "
            f"{knowledge_hit_count} extrait(s) documentaire(s) pertinent(s) trouvé(s). "
            "Le service IA distant est indisponible ou sans quota."
        )

    @staticmethod
    def _format_knowledge_context(chunks: list) -> str:
        if not chunks:
            return "Aucun contexte documentaire pertinent retrouvé."

        return "\n\n".join(
            f"[S{index}] {chunk.title} — {chunk.content}"
            for index, chunk in enumerate(chunks, start=1)
        )

    @staticmethod
    def _build_citations(hits: list[KnowledgeSearchResult]) -> list[KnowledgeCitation]:
        return [
            KnowledgeCitation(
                citation_id=f"S{index}",
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                title=hit.title,
                source=hit.source,
                snippet=hit.snippet,
            )
            for index, hit in enumerate(hits, start=1)
        ]

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT


assistant_service = AssistantService()
