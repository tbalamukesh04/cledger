"""Add transaction_audit table

Revision ID: 26aea3793024
Revises: 079341ba1d7d
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '26aea3793024'
down_revision: Union[str, Sequence[str], None] = 'c583c2feef3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'transaction_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('actor_identifier', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_transaction_audit_transaction_id'),
        'transaction_audit',
        ['transaction_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_transaction_audit_created_at'),
        'transaction_audit',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_transaction_audit_created_at'), table_name='transaction_audit')
    op.drop_index(op.f('ix_transaction_audit_transaction_id'), table_name='transaction_audit')
    op.drop_table('transaction_audit')
