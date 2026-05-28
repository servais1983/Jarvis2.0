from __future__ import annotations

from collections.abc import Sequence
from math import sqrt

from openai import OpenAI

from jarvis_cyber.config import settings


class EmbeddingService:
    """Small wrapper around embeddings with a local-disabled fallback."""

    def __init__(self) -> None:
        self._client = (
            OpenAI(api_key=settings.openai_api_key.get_secret_value())
            if settings.openai_api_key
            else None
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._client is None:
            return []

        kwargs = {
            "model": settings.embedding_model,
            "input": list(texts),
        }
        if settings.embedding_dimensions is not None:
            kwargs["dimensions"] = settings.embedding_dimensions

        response = self._client.embeddings.create(**kwargs)
        return [item.embedding for item in response.data]

    @staticmethod
    def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = sqrt(sum(a * a for a in left))
        right_norm = sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)


embedding_service = EmbeddingService()
