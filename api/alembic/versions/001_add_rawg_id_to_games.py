"""add rawg_id to games table

Revision ID: 001_add_rawg_id
Revises: None
Create Date: 2026-09-27 15:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_rawg_id'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('games', sa.Column('rawg_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_games_rawg_id'), 'games', ['rawg_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_games_rawg_id'), table_name='games')
    op.drop_column('games', 'rawg_id')
