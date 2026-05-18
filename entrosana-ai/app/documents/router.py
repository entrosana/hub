"""FastAPI routes for documents."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import repository, service
from app.documents.schemas import DocumentIn, DocumentOut
from app.core.dependencies import get_db, get_tenant_id

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=list[DocumentOut])
async def list_(
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_all(db, tenant_id, limit=limit)


@router.post("/", response_model=DocumentOut, status_code=201)
async def create(
    payload: DocumentIn,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    obj = await service.create_document(
        db, tenant_id=tenant_id, actor_id="system", name=payload.name,
    )
    await db.commit()
    return obj
