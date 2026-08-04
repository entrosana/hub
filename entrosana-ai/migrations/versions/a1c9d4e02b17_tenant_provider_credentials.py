"""tenant provider credentials

Revision ID: a1c9d4e02b17
Revises: f8a4963007ac
Create Date: 2026-08-04 15:20:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'a1c9d4e02b17'
down_revision = 'f8a4963007ac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('providers_tenant_credentials',
    sa.Column('provider_name', sa.String(length=64), nullable=False),
    sa.Column('setting_name', sa.String(length=64), nullable=False),
    sa.Column('encrypted_value', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint(
        'tenant_id', 'provider_name', 'setting_name',
        name='uq_providers_tenant_credentials_tenant_provider_setting',
    )
    )
    op.create_index(
        op.f('ix_providers_tenant_credentials_tenant_id'),
        'providers_tenant_credentials', ['tenant_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_providers_tenant_credentials_tenant_id'),
        table_name='providers_tenant_credentials',
    )
    op.drop_table('providers_tenant_credentials')
