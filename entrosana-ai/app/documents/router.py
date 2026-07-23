"""FastAPI routes for documents."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import list_for_tenant
from app.core.dependencies import get_actor_id, get_db, get_tenant_id
from app.documents import repository, service
from app.documents.models import Document
from app.documents.schemas import DocumentIn, DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    classification: str | None = None,
    limit: int = 50,
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if classification:
        return await repository.list_by_classification(db, tenant_id, classification, limit=limit)
    return await list_for_tenant(db, Document, tenant_id, limit=limit)


@router.post("/", response_model=DocumentOut, status_code=201)
async def register_document(
    payload: DocumentIn,
    tenant_id: UUID = Depends(get_tenant_id),
    actor_id: str = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
):
    document = await service.register_document(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        filename=payload.filename,
        mime_type=payload.mime_type,
        storage_uri=payload.storage_uri,
        size_bytes=payload.size_bytes,
    )
    await db.commit()
    return document
