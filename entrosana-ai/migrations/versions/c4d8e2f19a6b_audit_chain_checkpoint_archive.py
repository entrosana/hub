"""add audit chain checkpoints and archive

Revision ID: c4d8e2f19a6b
Revises: f8a4963007ac
Create Date: 2026-07-24 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c4d8e2f19a6b"
down_revision = "f8a4963007ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_chain_checkpoint",
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("hmac", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_audit_checkpoint_tenant"),
    )
    op.create_index(
        op.f("ix_audit_chain_checkpoint_tenant_id"),
        "audit_chain_checkpoint",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "audit_events_archive",
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=False),
        sa.Column("after_state", sa.JSON(), nullable=False),
        sa.Column("reasoning", sa.String(), nullable=True),
        sa.Column("prev_hmac", sa.String(length=64), nullable=False),
        sa.Column("hmac", sa.String(length=64), nullable=False),
        sa.Column("key_id", sa.String(length=32), server_default="k1", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "seq", name="uq_audit_archive_tenant_seq"),
    )
    op.create_index(
        op.f("ix_audit_events_archive_action"),
        "audit_events_archive",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_archive_hmac"),
        "audit_events_archive",
        ["hmac"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_archive_tenant_id"),
        "audit_events_archive",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_archive_tenant_id"), table_name="audit_events_archive")
    op.drop_index(op.f("ix_audit_events_archive_hmac"), table_name="audit_events_archive")
    op.drop_index(op.f("ix_audit_events_archive_action"), table_name="audit_events_archive")
    op.drop_table("audit_events_archive")
    op.drop_index(
        op.f("ix_audit_chain_checkpoint_tenant_id"),
        table_name="audit_chain_checkpoint",
    )
    op.drop_table("audit_chain_checkpoint")
