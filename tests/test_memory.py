import json

from jarvis_cyber.memory.store import SQLiteMemoryStore
from jarvis_cyber.storage.database import Database


def test_memory_store_round_trip(monkeypatch, tmp_path) -> None:
    local_database = Database(tmp_path / "memory.db")
    monkeypatch.setattr("jarvis_cyber.memory.store.database", local_database)
    store = SQLiteMemoryStore()

    store.append("user-a", "alpha", "user", "premier message")
    store.append("user-a", "alpha", "assistant", "première réponse")
    store.append("user-b", "beta", "user", "autre session")

    turns = store.recent("user-a", "alpha", limit=10)

    assert len(turns) == 2
    assert [turn.role for turn in turns] == ["user", "assistant"]


def test_memory_store_migrates_legacy_jsonl(monkeypatch, tmp_path) -> None:
    local_database = Database(tmp_path / "memory.db")
    monkeypatch.setattr("jarvis_cyber.memory.store.database", local_database)
    (tmp_path / "conversations.jsonl").write_text(
        json.dumps(
            {
                "session_id": "legacy",
                "role": "user",
                "content": "bonjour",
                "created_at": "2026-05-16T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    store = SQLiteMemoryStore(tmp_path)

    assert store.recent("local-dev", "legacy", limit=5)[0].content == "bonjour"
