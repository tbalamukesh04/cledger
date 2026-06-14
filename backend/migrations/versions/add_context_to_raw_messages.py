"""add business_id and phone_number_id context to raw_messages

Revision ID: 3c4d5e6f7g8h
Revises: 2b3c4d5e6f7g
Create Date: 2026-06-14 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3c4d5e6f7g8h'
down_revision = '2b3c4d5e6f7g'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('raw_messages', sa.Column('business_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_raw_messages_business_id'), 'raw_messages', ['business_id'], unique=False)
    
    op.add_column('raw_messages', sa.Column('phone_number_id', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_raw_messages_phone_number_id'), 'raw_messages', ['phone_number_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_raw_messages_phone_number_id'), table_name='raw_messages')
    op.drop_column('raw_messages', 'phone_number_id')
    
    op.drop_index(op.f('ix_raw_messages_business_id'), table_name='raw_messages')
    op.drop_column('raw_messages', 'business_id')
