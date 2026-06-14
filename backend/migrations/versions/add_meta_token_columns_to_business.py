"""add meta token columns to businesses

Revision ID: 1a2b3c4d5e6f
Revises: yyy_enforce_tenant_constraints
Create Date: 2026-06-14 15:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = 'yyy_enforce_tenant_constraints'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('businesses', sa.Column('meta_access_token', sa.Text(), nullable=True))
    op.add_column('businesses', sa.Column('meta_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('businesses', sa.Column('meta_business_account_id', sa.String(), nullable=True))
    op.add_column('businesses', sa.Column('meta_token_last_refreshed_at', sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column('businesses', 'meta_token_last_refreshed_at')
    op.drop_column('businesses', 'meta_business_account_id')
    op.drop_column('businesses', 'meta_token_expires_at')
    op.drop_column('businesses', 'meta_access_token')
