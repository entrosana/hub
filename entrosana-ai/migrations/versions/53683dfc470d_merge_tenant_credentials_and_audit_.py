"""merge tenant credentials and audit chain heads

Revision ID: 53683dfc470d
Revises: a1c9d4e02b17, c4d8e2f19a6b
Create Date: 2026-08-05 17:19:13.529238

"""
from alembic import op
import sqlalchemy as sa


revision = '53683dfc470d'
down_revision = ('a1c9d4e02b17', 'c4d8e2f19a6b')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
