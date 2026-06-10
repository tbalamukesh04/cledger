"""create businesses table and backfill

Revision ID: c7b4171aafda
Revises: ebb5d34ec39f
Create Date: 2026-06-09 14:54:34.200755

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

# revision identifiers, used by Alembic.
revision = 'c7b4171aafda'
down_revision = 'ebb5d34ec39f'
branch_labels = None
depends_on = None

def upgrade():
    # Stage A: Create businesses table
    businesses_table = op.create_table(
        'businesses',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('auth0_org_id', sa.String(), nullable=True),
        sa.Column('meta_waba_id', sa.String(), nullable=True),
        sa.Column('meta_phone_number_id', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)
    )

    # Create tenant-aware indexes
    op.create_index(op.f('ix_businesses_slug'), 'businesses', ['slug'], unique=True)
    op.create_index(op.f('ix_businesses_auth0_org_id'), 'businesses', ['auth0_org_id'], unique=False)
    op.create_index(op.f('ix_businesses_meta_waba_id'), 'businesses', ['meta_waba_id'], unique=False)

    # Stage B: Seed Default Legacy Tenant
    # We use bulk_insert to ensure the ID is explicitly 1 for the backfill
    op.bulk_insert(
        businesses_table,
        [
            {
                "id": 1,
                "name": "Legacy Default",
                "slug": "legacy-default",
                "is_active": True,
            }
        ]
    )

    # Stage C: Fast SQL-Level Backfill
    # Updates existing records to map to the Legacy Default tenant
    tables_to_backfill = ['groups', 'participants', 'raw_messages', 'transactions']
    for tbl in tables_to_backfill:
        op.execute(f"UPDATE {tbl} SET tenant_id = 1 WHERE tenant_id IS NULL")

def downgrade():
    # Reverse backfill (Optional, but good for pure idempotency)
    tables_to_backfill = ['groups', 'participants', 'raw_messages', 'transactions']
    for tbl in tables_to_backfill:
        op.execute(f"UPDATE {tbl} SET tenant_id = NULL WHERE tenant_id = 1")

    # Drop indexes and table
    op.drop_index(op.f('ix_businesses_meta_waba_id'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_auth0_org_id'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_slug'), table_name='businesses')
    op.drop_table('businesses')
