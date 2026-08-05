"""Business logic for documents. All mutations route through audit.record()."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.crud import create_for_tenant
from app.core.validation import require_non_empty, require_range
from app.documents.models import Document


async def register_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: str,
    filename: str,
    mime_type: str,
    storage_uri: str,
    size_bytes: int,
) -> Document:
    """Persist a document row. The actual upload to object storage
    happens upstream; this service just records the metadata pointer."""
    filename = require_non_empty(filename, "filename")
    mime_type = require_non_empty(mime_type, "mime_type")
    storage_uri = require_non_empty(storage_uri, "storage_uri")
    size_bytes = require_range(size_bytes, "size_bytes", min=0, max=2**63 - 1)
    document = await create_for_tenant(
        db,
        Document,
        tenant_id,
        filename=filename,
        mime_type=mime_type,
        storage_uri=storage_uri,
        size_bytes=size_bytes,
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="documents.document.register",
        target_type="document",
        target_id=str(document.id),
        after={
            "filename": filename,
            "mime_type": mime_type,
            "storage_uri": storage_uri,
            "size_bytes": size_bytes,
        },
    )
    return document
