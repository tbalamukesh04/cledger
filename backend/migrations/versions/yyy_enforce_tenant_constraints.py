"""enforce tenant constraints

Revision ID: yyyy_enforce_tenant_constraints
Revises: c7b4171aafda
Create Date: 2026-06-09

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'yyy_enforce_tenant_constraints'
down_revision = 'c7b4171aafda' # Points to the migration above
branch_labels = None
depends_on = None

def upgrade():
    # Stage D: Apply Foreign Key Constraints and Set NOT NULL
    # This is safe to execute because the previous migration guaranteed no NULLs remain.
    tables = ['groups', 'participants', 'raw_messages', 'transactions']
    
    for tbl in tables:
        # 1. Enforce NOT NULL
        op.alter_column(tbl, 'tenant_id', existing_type=sa.Integer(), nullable=False)
        
        # 2. Add explicit Foreign Key with restricted deletion
        op.create_foreign_key(
            f'fk_{tbl}_tenant_id_businesses',
            source_table=tbl,
            referent_table='businesses',
            local_cols=['tenant_id'],
            remote_cols=['id'],
            ondelete='RESTRICT' # Prevents accidental deletion of a tenant that still has data
        )

def downgrade():
    tables = ['groups', 'participants', 'raw_messages', 'transactions']
    
    for tbl in tables:
        # 1. Drop Foreign Key
        op.drop_constraint(f'fk_{tbl}_tenant_id_businesses', table_name=tbl, type_='foreignkey')
        
        # 2. Revert to nullable
        op.alter_column(tbl, 'tenant_id', existing_type=sa.Integer(), nullable=True)