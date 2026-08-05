"""merge tenant credentials and audit chain heads

Revision ID: 0c13113d2290
Revises: a1c9d4e02b17, c4d8e2f19a6b
Create Date: 2026-08-05 16:57:16.658071

"""
from alembic import op
import sqlalchemy as sa


revision = '0c13113d2290'
down_revision = ('a1c9d4e02b17', 'c4d8e2f19a6b')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
