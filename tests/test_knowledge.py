from jarvis_cyber.knowledge.store import SQLiteKnowledgeStore
from jarvis_cyber.storage.database import Database


def test_knowledge_store_add_and_search(tmp_path) -> None:
    store = SQLiteKnowledgeStore(
        tmp_path,
        chunk_size=80,
        chunk_overlap=10,
        db=Database(tmp_path / "knowledge.db"),
    )
    document = store.add_document(
        "user-a",
        "Playbook phishing",
        "Pour un phishing, vérifier les en-têtes email, les URLs, les pièces jointes et l'utilisateur ciblé.",
        source="playbook.md",
    )

    results = store.search("user-a", "phishing urls", limit=3)

    assert document.title == "Playbook phishing"
    assert results
    assert results[0].title == "Playbook phishing"


def test_knowledge_store_lists_documents(tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    store.add_document("user-a", "Procédure SOC", "Escalader les alertes critiques.", source="soc.md")

    documents = store.list_documents("user-a")

    assert len(documents) == 1
    assert documents[0].source == "soc.md"


def test_knowledge_store_deduplicates_documents(tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    first = store.add_document("user-a", "Playbook A", "Toujours vérifier les URLs.", source="a.md")
    second = store.add_document("user-a", "Playbook B", "Toujours vérifier les URLs.", source="b.md")

    documents = store.list_documents("user-a")

    assert len(documents) == 1
    assert first.document_id == second.document_id


def test_knowledge_store_allows_same_content_for_distinct_users(tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    first = store.add_document("user-a", "Playbook A", "Toujours vérifier les URLs.", source="a.md")
    second = store.add_document("user-b", "Playbook B", "Toujours vérifier les URLs.", source="b.md")

    assert first.document_id != second.document_id
    assert len(store.list_documents("user-a")) == 1
    assert len(store.list_documents("user-b")) == 1


def test_knowledge_store_deletes_document(tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    document = store.add_document("user-a", "Procédure SOC", "Escalader les alertes critiques.", source="soc.md")

    deleted = store.delete_document("user-a", document.document_id)

    assert deleted is True
    assert store.list_documents("user-a") == []
    assert store.search("user-a", "alertes", limit=3) == []


def test_knowledge_store_reads_legacy_documents(tmp_path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    documents_path.write_text(
        '{"document_id":"legacy","title":"Ancien","source":"legacy.md","content":"Ancien contenu","created_at":"2026-05-16T00:00:00+00:00"}\n',
        encoding="utf-8",
    )
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))

    documents = store.list_documents("local-dev")

    assert documents[0].document_id == "legacy"
    assert documents[0].content_hash


def test_knowledge_store_uses_semantic_search_when_embeddings_exist(monkeypatch, tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    monkeypatch.setattr("jarvis_cyber.knowledge.store.embedding_service._client", object())
    monkeypatch.setattr(
        "jarvis_cyber.knowledge.store.embedding_service.embed",
        lambda texts: [[1.0, 0.0] for _ in texts],
    )
    document = store.add_document("user-a", "VPN", "Réinitialiser le tunnel sécurisé.", source="vpn.md")

    results = store.search("user-a", "connexion distante", limit=3)

    assert document.title == "VPN"
    assert results[0].search_mode == "semantic"
