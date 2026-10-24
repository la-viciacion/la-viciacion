"""game_dlc_link: mark a DLC and link it to its base game by id

Revision ID: 039_game_dlc_link
Revises: 038_game_parent
Create Date: 2026-10-24 18:00:00.000000

038 kept the RAWG id of the base game, which cannot describe a game created by hand (no RAWG id, and a base that
may not have one either) nor a DLC whose base is unknown. This replaces it with what the app needs:
`games.is_dlc` (the game is a DLC / expansion / edition) and `games.parent_game_id` (its base game in the
catalogue, optional: a DLC can be marked without one). The link is a foreign key to `games.id`, ON DELETE SET NULL,
so deleting a base game leaves its DLCs marked and unlinked.

Data: for every game with a `parent_rawg_id`, `is_dlc` is set and `parent_game_id` points at the catalogue game that
has that RAWG id (left empty when there is none or the id is the game's own). Nothing else is read or rewritten.
`parent_rawg_id` is then dropped: it only ever existed in 038, in this same change, and was filled by the app alone.
The new link column is created with the type and collation of `games.id`, which a foreign key needs.

Re-runnable: each step checks what is already there; the old column is dropped only after the backfill.

Downgrade: restores `parent_rawg_id` from the base game's RAWG id and drops the new columns. A DLC marked without
a base game, or whose base has no RAWG id, loses its mark.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '039_game_dlc_link'
down_revision: Union[str, None] = '038_game_parent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
KEY = 'fk_games_parent'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _keys() -> set[str]:
    return {fk['name'] for fk in sa.inspect(op.get_bind()).get_foreign_keys(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns()
    if 'is_dlc' not in columns:
        op.add_column(TABLE, sa.Column('is_dlc', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    if 'parent_game_id' not in columns:
        kind, collation = bind.execute(sa.text(
            'SELECT column_type, collation_name FROM information_schema.columns '
            "WHERE table_schema = DATABASE() AND table_name = 'games' AND column_name = 'id'"
        )).one()
        # the type and collation come from the catalogue itself, never from the caller
        bind.execute(sa.text(f'ALTER TABLE games ADD COLUMN parent_game_id {kind} COLLATE {collation} NULL'))
    if 'parent_rawg_id' in _columns():
        bind.execute(sa.text('UPDATE games SET is_dlc = 1 WHERE parent_rawg_id IS NOT NULL'))
        bind.execute(sa.text(
            'UPDATE games child JOIN games base ON base.rawg_id = child.parent_rawg_id AND base.id <> child.id '
            'SET child.parent_game_id = base.id '
            'WHERE child.parent_rawg_id IS NOT NULL AND child.parent_game_id IS NULL'
        ))
    if KEY not in _keys():
        op.create_foreign_key(KEY, TABLE, TABLE, ['parent_game_id'], ['id'], ondelete='SET NULL')
    if 'parent_rawg_id' in _columns():
        op.drop_column(TABLE, 'parent_rawg_id')


def downgrade() -> None:
    bind = op.get_bind()
    if 'parent_rawg_id' not in _columns():
        op.add_column(TABLE, sa.Column('parent_rawg_id', sa.Integer(), nullable=True))
    if 'parent_game_id' in _columns():
        bind.execute(sa.text(
            'UPDATE games child JOIN games base ON base.id = child.parent_game_id '
            'SET child.parent_rawg_id = base.rawg_id WHERE child.parent_rawg_id IS NULL'
        ))
    if KEY in _keys():
        op.drop_constraint(KEY, TABLE, type_='foreignkey')
    for name in ('parent_game_id', 'is_dlc'):
        if name in _columns():
            op.drop_column(TABLE, name)
