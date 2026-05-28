from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from jarvis_cyber.knowledge.extractors import (
    EmptyKnowledgeFileError,
    KnowledgeFileExtractor,
)


def test_extracts_text_file() -> None:
    extractor = KnowledgeFileExtractor()
    assert extractor.extract("note.md", b"Bonjour Jarvis") == "Bonjour Jarvis"


def test_extracts_docx_file() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Première ligne</w:t></w:r></w:p>
                <w:p><w:r><w:t>Deuxième ligne</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """.strip(),
        )

    extractor = KnowledgeFileExtractor()
    assert extractor.extract("rapport.docx", buffer.getvalue()) == "Première ligne Deuxième ligne"


def test_rejects_empty_text() -> None:
    extractor = KnowledgeFileExtractor()
    with pytest.raises(EmptyKnowledgeFileError):
        extractor.extract("empty.txt", b"   ")
