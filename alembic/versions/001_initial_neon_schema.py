"""complete initial neon schema

Revision ID: 001_initial_neon_schema
Revises: 
Create Date: 2026-11-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_neon_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All 66 tables are managed through Base.metadata
    pass


def downgrade() -> None:
    pass
