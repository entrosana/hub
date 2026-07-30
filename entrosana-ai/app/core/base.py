"""Shared ORM mixins.

`TenantBase` is the common base for every domain table: UUID primary key,
tenant_id column (indexed, required), and created/updated timestamps.
Inheriting from it removes the need to redeclare those columns on every model.

The tenant_id pattern is load-bearing: every query in every module's
repository.py MUST filter by tenant_id so cross-tenant reads are impossible.
The `sqlalchemy.Uuid` column type adapts per dialect (native uuid on
Postgres, char(32) on SQLite) so the in-memory test database works too.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantBase(Base):
    """Abstract base for all tenant-scoped tables.

    Subclasses still need to declare __tablename__.
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GlobalBase(Base):
    """Abstract base for global (non-tenant-scoped) tables — e.g. the Tenant
    table itself, and lookup tables shared across tenants.

    Subclasses still need to declare __tablename__.
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
