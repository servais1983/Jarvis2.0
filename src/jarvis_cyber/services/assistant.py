import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Callable, TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from jarvis_cyber.config import settings
from jarvis_cyber.core.prompts import SYSTEM_PROMPT
from jarvis_cyber.core.schemas import KnowledgeCitation, KnowledgeSearchResult
from jarvis_cyber.inbox.store import inbox_store
from jarvis_cyber.knowledge.store import knowledge_store
from jarvis_cyber.memory.store import memory_store
from jarvis_cyber.playbooks.store import playbook_store
from jarvis_cyber.profile.store import profile_store
from jarvis_cyber.services.brain import brain_status
from jarvis_cyber.services.connector_context import connector_context_service
from jarvis_cyber.services.local_agent import (
    LocalAgentUnavailableError,
    local_agent_service,
)
from jarvis_cyber.services.tool_catalog import tool_catalog_service

logger = logging.getLogger(__name__)


_LOCAL_HISTORY_TURNS = 8
_FALLBACK_REMINDER_SECONDS = 600

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
    ) -> tuple[str, str, bool, list[KnowledgeSearchResult], list[KnowledgeCitation], list[str]]:
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
            "avec le format [S1], [S2], etc.\n\n"
            f"{self._spoken_style(user_id)}"
        )
        history_payload = [{"role": turn.role, "content": turn.content} for turn in history]

        # 1) Moteur local d'abord : Ollama, avec les outils MCP à sa disposition.
        # Un petit modèle se perd dans un long prompt : il reçoit l'essentiel, et
        # seulement les derniers échanges.
        started = time.monotonic()
        local_result = self._try_local_agent(
            message,
            history_payload[-_LOCAL_HISTORY_TURNS:],
            self._conversation_prompt(
                user_id, playbook_context, inbox_context, context_block, bool(knowledge_chunks)
            ),
        )
        if local_result is not None:
            logger.info(
                "Réponse %s en %.1f s, outils %s : %r → %r",
                local_result.model,
                time.monotonic() - started,
                local_result.tools_used,
                message[:120],
                local_result.answer[:160],
            )
            memory_store.append(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=local_result.answer,
            )
            return (
                local_result.answer,
                local_result.model,
                False,
                knowledge_hits,
                citations,
                local_result.tools_used,
            )

        # 2) Modèle distant OpenAI si configuré
        if self._client is None:
            # Non mémorisé : un message de repli répété embrouillerait le modèle ensuite
            answer = self._local_chat_fallback(message, len(knowledge_hits))
            return answer, settings.main_model, False, knowledge_hits, citations, []

        try:
            response = self._respond_with_tools(
                user_id=user_id,
                role=role,
                instructions=instructions,
                history=history_payload,
            )
        except OpenAIError:
            # Non mémorisé : un message de repli répété embrouillerait le modèle ensuite
            answer = self._local_chat_fallback(message, len(knowledge_hits))
            return answer, settings.main_model, False, knowledge_hits, citations, []
        answer = response.output_text
        memory_store.append(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=answer,
        )
        return answer, settings.main_model, True, knowledge_hits, citations, []

    @classmethod
    def _conversation_prompt(
        cls,
        user_id: str,
        playbook_context: str,
        inbox_context: str,
        knowledge_context: str,
        has_knowledge: bool,
    ) -> str:
        """Prompt du modèle local : qui il est, la date, quand utiliser un outil."""
        name = profile_store.get(user_id).display_name or settings.user_name
        now = datetime.now()
        parts = [
            f"Tu es Jarvis, l'assistant personnel de {name}, dans l'esprit de celui d'Iron Man : "
            "calme, précis, un peu d'esprit, jamais bavard.",
            f"Nous sommes le {now.strftime('%d/%m/%Y')} et il est {now.strftime('%H:%M')}.",
            "Tu disposes d'outils pour agir sur son ordinateur : ouvrir une application ou un "
            "site, chercher sur le web, régler le son, lire l'état de la machine, calculer. "
            "Appelle un outil uniquement quand la demande l'exige. Pour une question de "
            "culture générale, un avis ou une conversation, réponds directement, sans outil. "
            "N'invente jamais le résultat d'un outil et n'annonce pas une action que tu n'as "
            "pas faite. Si tu ne sais pas ou si tu as mal compris, dis-le en une phrase et "
            "demande de préciser.",
            "Réponds à la dernière demande seulement, sans répéter ce que tu as déjà dit.",
            "Tu es aussi compétent en cybersécurité quand on t'en parle.",
            cls._spoken_style(user_id),
        ]
        if has_knowledge:
            parts.append(f"Extraits de sa base documentaire, à citer [S1], [S2] :\n{knowledge_context}")
        if not playbook_context.startswith("Aucun playbook"):
            parts.append(f"Ses procédures qui peuvent s'appliquer :\n{playbook_context}")
        if not inbox_context.startswith("Aucun élément"):
            parts.append(f"Éléments non lus dans son inbox :\n{inbox_context}")
        return "\n\n".join(parts)

    @staticmethod
    def _spoken_style(user_id: str) -> str:
        """Consignes de forme : la réponse est dite à voix haute par l'orb."""
        name = profile_store.get(user_id).display_name or settings.user_name
        return (
            "Ta réponse est lue à voix haute par une synthèse vocale. Réponds en français, "
            "en phrases courtes et naturelles, sans liste à puces, sans markdown, sans "
            "symboles ni tableaux, et en trois phrases au plus sauf si on te demande le "
            f"détail. Tu t'adresses à {name} par son prénom. Quand un outil te donne un "
            "résultat, dis-le simplement sans décrire l'outil."
        )

    @staticmethod
    def _try_local_agent(message: str, history: list[dict], system_prompt: str):
        """Tente une réponse via Ollama + outils MCP ; None si indisponible."""

        async def run():
            if not await local_agent_service.available():
                return None
            return await local_agent_service.chat(
                message=message,
                history=history,
                system_prompt=system_prompt,
            )

        try:
            return asyncio.run(run())
        except LocalAgentUnavailableError as exc:
            logger.info("Agent local indisponible : %s", exc)
            return None
        except Exception as exc:  # le chat ne doit jamais casser pour un souci local
            logger.warning("Agent local en erreur : %s", exc, exc_info=True)
            return None

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
            except Exception as exc:
                logger.error("Tool execution failed: %s — %s", call.name, exc, exc_info=True)
                result = {"error": "tool_execution_failed", "tool": call.name}
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

    # Dernière cause de repli annoncée, pour ne pas redire la même explication à chaque question
    _last_fallback: tuple[str, float] = ("", float("-inf"))

    @classmethod
    def _local_chat_fallback(cls, message: str, knowledge_hit_count: int) -> str:
        """Phrase dite quand aucun modèle n'a pu répondre : elle nomme la vraie cause."""
        brain = brain_status()
        if brain["engine"] == "ollama":
            cause = "timeout"
            full = "Mon moteur de langage n'a pas répondu à temps. Redemande-moi."
            short = full
        elif brain["pull"] == "running":
            cause = "pull"
            full = (
                f"Je télécharge encore mon modèle de langage {brain['model']}. "
                "Mes commandes directes fonctionnent déjà ; pour le reste, redemande-moi "
                "dans quelques minutes."
            )
            short = "Mon modèle de langage est toujours en cours de téléchargement."
        elif brain["ollama_running"]:
            cause = "missing"
            full = (
                f"Ollama tourne, mais le modèle {brain['model']} n'est pas installé : "
                "je ne peux pas répondre à cette question libre."
            )
            short = f"Le modèle {brain['model']} n'est toujours pas installé."
        else:
            cause = "none"
            found = (
                f" J'ai trouvé {knowledge_hit_count} extrait(s) dans ta base documentaire."
                if knowledge_hit_count
                else ""
            )
            full = (
                "Je fonctionne en mode local, sans moteur de langage : je ne peux pas répondre "
                "à cette question libre. Lance Ollama pour me donner un cerveau ; mes commandes "
                f"directes restent disponibles.{found}"
            )
            short = "Je n'ai toujours pas de moteur de langage pour répondre à ça."

        previous_cause, previous_at = cls._last_fallback
        now = time.monotonic()
        cls._last_fallback = (cause, now)
        repeated = previous_cause == cause and now - previous_at < _FALLBACK_REMINDER_SECONDS
        return short if repeated else full

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
