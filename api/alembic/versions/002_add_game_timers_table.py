"""add game_timers table

Revision ID: 002_add_game_timers
Revises: 001_add_rawg_id
Create Date: 2026-09-28 07:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_game_timers'
down_revision: Union[str, None] = '001_add_rawg_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'game_timers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.String(length=255), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('platform', sa.String(length=255), nullable=True),
        sa.Column('season', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.UniqueConstraint('user_id', 'game_id', 'start_time', name='uq_game_timers_user_game_start'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_game_timers_user_id'), 'game_timers', ['user_id'], unique=False)
    op.create_index(op.f('ix_game_timers_game_id'), 'game_timers', ['game_id'], unique=False)
    op.create_index(op.f('ix_game_timers_is_active'), 'game_timers', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_game_timers_is_active'), table_name='game_timers')
    op.drop_index(op.f('ix_game_timers_game_id'), table_name='game_timers')
    op.drop_index(op.f('ix_game_timers_user_id'), table_name='game_timers')
    op.drop_table('game_timers')
