"""add waba subscription state columns

Revision ID: 2b3c4d5e6f7g
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-14 15:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2b3c4d5e6f7g'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('businesses', sa.Column('waba_subscription_status', sa.String(), nullable=True))
    op.add_column('businesses', sa.Column('waba_subscription_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('businesses', sa.Column('waba_subscription_error', sa.Text(), nullable=True))
    op.add_column('businesses', sa.Column('waba_last_subscription_check', sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column('businesses', 'waba_last_subscription_check')
    op.drop_column('businesses', 'waba_subscription_error')
    op.drop_column('businesses', 'waba_subscription_timestamp')
    op.drop_column('businesses', 'waba_subscription_status')
