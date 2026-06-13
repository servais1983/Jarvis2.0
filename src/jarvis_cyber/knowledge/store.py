from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearchResult,
)
from jarvis_cyber.knowledge.embeddings import embedding_service
from jarvis_cyber.storage.database import Database, database


MAX_DOCUMENT_SIZE = 500_000  # bytes — rejects documents larger than ~500 KB


class SQLiteKnowledgeStore:
    """Durable local knowledge store backed by SQLite."""

    def __init__(
        self,
        data_dir: str | Path = settings.data_dir,
        chunk_size: int = settings.knowledge_chunk_size,
        chunk_overlap: int = settings.knowledge_chunk_overlap,
        db: Database = database,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_documents_path = self.data_dir / "documents.jsonl"
        self.legacy_chunks_path = self.data_dir / "document_chunks.jsonl"
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.database = db
        self._migrate_legacy_if_needed()

    def add_document(
        self,
        user_id: str,
        title: str,
        content: str,
        source: str | None = None,
    ) -> KnowledgeDocument:
        if len(content.encode()) > MAX_DOCUMENT_SIZE:
            raise ValueError(
                f"Document exceeds maximum size of {MAX_DOCUMENT_SIZE // 1000} KB."
            )
        normalized_content = self._normalize_content(content)
        content_hash = self._hash_content(normalized_content)
        existing = self.find_by_hash(user_id, content_hash)
        if existing is not None:
            return existing

        created_at = datetime.now(UTC).isoformat()
        document = KnowledgeDocument(
            document_id=str(uuid4()),
            title=title,
            source=source,
            content=normalized_content,
            content_hash=content_hash,
            created_at=created_at,
        )
        chunk_contents = self._chunk_text(normalized_content)
        embeddings = embedding_service.embed(chunk_contents) if embedding_service.enabled else []

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_documents
                (document_id, user_id, title, source, content, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.document_id,
                    user_id,
                    document.title,
                    document.source,
                    document.content,
                    document.content_hash,
                    document.created_at,
                ),
            )
            for index, chunk_content in enumerate(chunk_contents):
                chunk = KnowledgeChunk(
                    chunk_id=f"{document.document_id}:{index}",
                    document_id=document.document_id,
                    title=title,
                    source=source,
                    content=chunk_content,
                    created_at=created_at,
                    embedding=embeddings[index] if embeddings else None,
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_chunks
                    (chunk_id, user_id, document_id, title, source, content, created_at, embedding_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        user_id,
                        chunk.document_id,
                        chunk.title,
                        chunk.source,
                        chunk.content,
                        chunk.created_at,
                        json.dumps(chunk.embedding) if chunk.embedding is not None else None,
                    ),
                )
        return document

    def list_documents(self, user_id: str) -> list[KnowledgeDocument]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, title, source, content, content_hash, created_at
                FROM knowledge_documents
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [KnowledgeDocument(**dict(row)) for row in rows]

    def find_by_hash(self, user_id: str, content_hash: str) -> KnowledgeDocument | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, title, source, content, content_hash, created_at
                FROM knowledge_documents
                WHERE user_id = ? AND content_hash = ?
                """,
                (user_id, content_hash),
            ).fetchone()
        return KnowledgeDocument(**dict(row)) if row is not None else None

    def delete_document(self, user_id: str, document_id: str) -> bool:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM knowledge_chunks WHERE user_id = ? AND document_id = ?",
                (user_id, document_id),
            )
            cursor = connection.execute(
                "DELETE FROM knowledge_documents WHERE user_id = ? AND document_id = ?",
                (user_id, document_id),
            )
        return cursor.rowcount > 0

    def search(self, user_id: str, query: str, limit: int) -> list[KnowledgeSearchResult]:
        semantic_results = self._semantic_search(user_id, query, limit)
        if semantic_results:
            return semantic_results
        return self._lexical_search(user_id, query, limit)

    def _lexical_search(self, user_id: str, query: str, limit: int) -> list[KnowledgeSearchResult]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        results: list[KnowledgeSearchResult] = []
        for chunk in self._all_chunks(user_id):
            chunk_terms = self._tokenize(chunk.content)
            overlap = query_terms & chunk_terms
            if not overlap:
                continue
            score = len(overlap) / len(query_terms)
            results.append(
                KnowledgeSearchResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    source=chunk.source,
                    snippet=self._snippet(chunk.content, overlap),
                    score=round(score, 4),
                    search_mode="lexical",
                )
            )
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def _semantic_search(self, user_id: str, query: str, limit: int) -> list[KnowledgeSearchResult]:
        if not embedding_service.enabled:
            return []
        query_embeddings = embedding_service.embed([query])
        if not query_embeddings:
            return []

        query_embedding = query_embeddings[0]
        results: list[KnowledgeSearchResult] = []
        for chunk in self._all_chunks(user_id):
            if not chunk.embedding:
                continue
            score = embedding_service.cosine_similarity(query_embedding, chunk.embedding)
            results.append(
                KnowledgeSearchResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    source=chunk.source,
                    snippet=self._snippet(chunk.content, set()),
                    score=round(score, 4),
                    search_mode="semantic",
                )
            )
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def chunks_for_results(
        self,
        user_id: str,
        results: list[KnowledgeSearchResult],
    ) -> list[KnowledgeChunk]:
        ids = {result.chunk_id for result in results}
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT chunk_id, document_id, title, source, content, created_at, embedding_json
                FROM knowledge_chunks
                WHERE user_id = ? AND chunk_id IN ({placeholders})
                """,
                (user_id, *tuple(ids)),
            ).fetchall()
        return [self._chunk_from_row(row) for row in rows]

    def _all_chunks(self, user_id: str) -> list[KnowledgeChunk]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, document_id, title, source, content, created_at, embedding_json
                FROM knowledge_chunks
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
        return [self._chunk_from_row(row) for row in rows]

    def _migrate_legacy_if_needed(self) -> None:
        with self.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
        if count > 0 or not self.legacy_documents_path.exists():
            return

        documents = self._read_jsonl(self.legacy_documents_path)
        chunks = self._read_jsonl(self.legacy_chunks_path)
        with self.database.connect() as connection:
            for payload in documents:
                upgraded = self._upgrade_document_payload(payload)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_documents
                    (document_id, user_id, title, source, content, content_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        upgraded["document_id"],
                        "local-dev",
                        upgraded["title"],
                        upgraded.get("source"),
                        upgraded["content"],
                        upgraded["content_hash"],
                        upgraded["created_at"],
                    ),
                )
            for payload in chunks:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_chunks
                    (chunk_id, user_id, document_id, title, source, content, created_at, embedding_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["chunk_id"],
                        "local-dev",
                        payload["document_id"],
                        payload["title"],
                        payload.get("source"),
                        payload["content"],
                        payload["created_at"],
                        json.dumps(payload.get("embedding"))
                        if payload.get("embedding") is not None
                        else None,
                    ),
                )

    def _chunk_text(self, content: str) -> list[str]:
        if len(content) <= self.chunk_size:
            return [content]
        chunks: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + self.chunk_size, len(content))
            chunks.append(content[start:end])
            if end == len(content):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    @staticmethod
    def _chunk_from_row(row) -> KnowledgeChunk:
        payload = dict(row)
        embedding_json = payload.pop("embedding_json")
        payload["embedding"] = json.loads(embedding_json) if embedding_json else None
        return KnowledgeChunk(**payload)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"\w+", text.lower()) if len(token) > 2}

    @staticmethod
    def _snippet(content: str, overlap: set[str]) -> str:
        lower = content.lower()
        positions = [lower.find(term) for term in overlap if lower.find(term) >= 0]
        start = max((min(positions) if positions else 0) - 80, 0)
        end = min(start + 240, len(content))
        return content[start:end]

    @staticmethod
    def _normalize_content(content: str) -> str:
        return " ".join(content.split())

    @staticmethod
    def _hash_content(content: str) -> str:
        return sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        payloads: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    payloads.append(json.loads(line))
        return payloads

    @classmethod
    def _upgrade_document_payload(cls, payload: dict) -> dict:
        if "content_hash" in payload:
            return payload
        upgraded = dict(payload)
        normalized_content = cls._normalize_content(payload["content"])
        upgraded["content"] = normalized_content
        upgraded["content_hash"] = cls._hash_content(normalized_content)
        return upgraded


knowledge_store = SQLiteKnowledgeStore()
