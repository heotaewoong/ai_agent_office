"""Local paragraph retrieval inside a single public source already read by the collector."""

from contextlib import closing
import re
import sqlite3
import unicodedata

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langsmith.run_helpers import tracing_context


MAX_PASSAGES = 12
_LEADING = 2
_STOP_WORDS = {
    "ai", "and", "for", "from", "how", "new", "of", "the", "to", "what", "with",
    "관련", "다음", "대한", "위해", "통해",
}


class ArticleParagraphRetriever(BaseRetriever):
    passages: list[Document]

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        words = re.findall(r"[^\W_]{2,}", unicodedata.normalize("NFKC", query).casefold())
        terms = list(dict.fromkeys(word for word in words if word not in _STOP_WORDS and not word.isdigit()))[:16]
        if not terms:
            return []
        # Prefix matching retains Korean postpositions without turning the title into FTS syntax.
        expression = " OR ".join(f'"{word}"*' for word in terms)
        try:
            with closing(sqlite3.connect(":memory:")) as db:
                db.execute("CREATE VIRTUAL TABLE source_passages USING fts5(body)")
                db.executemany("INSERT INTO source_passages(rowid, body) VALUES (?, ?)", (
                    (passage.metadata["number"], unicodedata.normalize("NFKC", passage.page_content))
                    for passage in self.passages
                ))
                matches = db.execute(
                    "SELECT rowid FROM source_passages WHERE source_passages MATCH ? AND rowid > ? "
                    "ORDER BY rank, rowid LIMIT ?",
                    (expression, _LEADING, MAX_PASSAGES - _LEADING),
                ).fetchall()
        except sqlite3.Error:
            return []
        if not matches:
            return []
        numbers = sorted([*range(1, _LEADING + 1), *(number for number, in matches)])
        return [self.passages[number - 1] for number in numbers]


def retrieve_paragraph_numbers(title: str, paragraphs: list[str]) -> list[int]:
    if len(paragraphs) <= MAX_PASSAGES:
        return []
    passages = [Document(page_content=text, metadata={"number": number})
                for number, text in enumerate(paragraphs, 1)]
    with tracing_context(enabled=False):
        matches = ArticleParagraphRetriever(passages=passages).invoke(title)
    return [passage.metadata["number"] for passage in matches]
