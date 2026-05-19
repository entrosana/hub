"""DB access for documents.

Generic CRUD lives in `app.core.crud`. Add document-specific queries
(by classification, awaiting OCR, by content hash) here.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document


async def list_by_classification(
    db: AsyncSession, tenant_id: UUID, classification: str, *, limit: int = 50
) -> list[Document]:
    q = (
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.classification == classification,
        )
        .order_by(Document.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars())
