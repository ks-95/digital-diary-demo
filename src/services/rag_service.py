"""Case-scoped, lexical retrieval for grounding document generation."""
import re
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import CaseDocumentChunk

TOKEN_RE = re.compile(r"[\w@.+/-]+", re.UNICODE)


def split_document(text: str, size: int = 1200, overlap: int = 180) -> list[str]:
    text = (text or "")[:120000].strip()
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [c for c in chunks if c]


def make_chunks(case_id: uuid.UUID, evidence_id: uuid.UUID, text: str) -> list[CaseDocumentChunk]:
    return [CaseDocumentChunk(case_id=case_id, evidence_id=evidence_id, chunk_index=i, content=chunk)
            for i, chunk in enumerate(split_document(text))]


async def retrieve_case_context(db: AsyncSession, case_id: uuid.UUID, queries: list[str], limit: int = 24) -> list[dict]:
    rows = (await db.execute(select(CaseDocumentChunk).where(CaseDocumentChunk.case_id == case_id))).scalars().all()
    if not rows:
        return []
    query_terms = set()
    for query in queries:
        query_terms.update(t.lower() for t in TOKEN_RE.findall(query or "") if len(t) > 1)
    scored = []
    for row in rows:
        terms = [t.lower() for t in TOKEN_RE.findall(row.content)]
        counts = Counter(terms)
        score = sum((1 + (count / (count + 1))) for term, count in counts.items() if term in query_terms)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_index))
    return [{"source_id": str(row.evidence_id), "chunk": row.chunk_index, "text": row.content}
            for _, row in scored[:limit]]
