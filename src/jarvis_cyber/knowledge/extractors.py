from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from pypdf import PdfReader


class UnsupportedKnowledgeFileError(ValueError):
    """Raised when a file cannot be ingested by the current MVP."""


class EmptyKnowledgeFileError(ValueError):
    """Raised when extraction succeeds technically but yields no usable text."""


class KnowledgeFileExtractor:
    """Extract plain text from supported knowledge-base file types."""

    supported_suffixes = {".txt", ".md", ".markdown", ".log", ".pdf", ".docx"}

    def extract(self, filename: str, raw_bytes: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.supported_suffixes:
            raise UnsupportedKnowledgeFileError(filename)

        if suffix in {".txt", ".md", ".markdown", ".log"}:
            text = raw_bytes.decode("utf-8")
        elif suffix == ".pdf":
            text = self._extract_pdf(raw_bytes)
        else:
            text = self._extract_docx(raw_bytes)

        normalized = " ".join(text.split())
        if not normalized:
            raise EmptyKnowledgeFileError(filename)
        return normalized

    @staticmethod
    def _extract_pdf(raw_bytes: bytes) -> str:
        reader = PdfReader(BytesIO(raw_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _extract_docx(raw_bytes: bytes) -> str:
        with ZipFile(BytesIO(raw_bytes)) as archive:
            xml = archive.read("word/document.xml")

        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
            joined = "".join(texts).strip()
            if joined:
                paragraphs.append(joined)
        return "\n".join(paragraphs)


knowledge_file_extractor = KnowledgeFileExtractor()
