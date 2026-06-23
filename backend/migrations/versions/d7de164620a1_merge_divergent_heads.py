"""merge divergent heads

Revision ID: d7de164620a1
Revises: 3c4d5e6f7g8h, dbd74f17bcf3
Create Date: 2026-06-15 16:04:00.027184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7de164620a1'
down_revision: Union[str, Sequence[str], None] = ('3c4d5e6f7g8h', 'dbd74f17bcf3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
