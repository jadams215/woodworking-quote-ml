"""Add project_type to quotes

Revision ID: b10c20d30e40
Revises: a1b2c3d4e5f6
Create Date: 2026-02-16 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b10c20d30e40'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add project_type column to quotes table
    op.add_column('quotes', sa.Column('project_type', sa.String(length=50), nullable=True))


def downgrade() -> None:
    # Remove project_type column from quotes table
    op.drop_column('quotes', 'project_type')
