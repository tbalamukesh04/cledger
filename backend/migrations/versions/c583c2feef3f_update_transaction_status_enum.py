"""update_transaction_status_enum

Revision ID: c583c2feef3f
Revises: 55d454f85b4e
Create Date: 2026-03-22 17:27:23.698714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c583c2feef3f'
down_revision: Union[str, Sequence[str], None] = '55d454f85b4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Create the enum type in PostgreSQL
    transaction_status_enum = postgresql.ENUM('parsed', 'review_needed', 'corrected', 'invalidated', name='transaction_status_enum')
    transaction_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. Drop the old check constraint safely
    op.execute('ALTER TABLE transactions DROP CONSTRAINT IF EXISTS check_status_type')

    # 3. Migrate existing data to match new enum values to avoid casting errors
    op.execute("UPDATE transactions SET status = 'parsed' WHERE status = 'accepted'")
    op.execute("UPDATE transactions SET status = 'review_needed' WHERE status = 'review_required'")
    op.execute("UPDATE transactions SET status = 'invalidated' WHERE status IN ('rejected', 'NOT PARSED')")

    # 4. Alter the column to use the new enum type
    op.execute('ALTER TABLE transactions ALTER COLUMN status DROP DEFAULT')
    op.execute('''
        ALTER TABLE transactions 
        ALTER COLUMN status TYPE transaction_status_enum 
        USING status::text::transaction_status_enum
    ''')
    op.execute("ALTER TABLE transactions ALTER COLUMN status SET DEFAULT 'review_needed'")

def downgrade() -> None:
    # 1. Migrate data back to old string values
    op.execute("UPDATE transactions SET status = 'accepted' WHERE status = 'parsed'")
    op.execute("UPDATE transactions SET status = 'review_required' WHERE status = 'review_needed'")
    op.execute("UPDATE transactions SET status = 'rejected' WHERE status = 'invalidated'") 
    op.execute("UPDATE transactions SET status = 'NOT PARSED' WHERE status = 'invalidated'") # Note: minor overlap in downgrade logic, but covers bounds

    # 2. Alter column back to Text
    op.execute('ALTER TABLE transactions ALTER COLUMN status DROP DEFAULT')
    op.execute('ALTER TABLE transactions ALTER COLUMN status TYPE TEXT USING status::text')
    op.execute("ALTER TABLE transactions ALTER COLUMN status SET DEFAULT 'review_required'")

    # 3. Re-add the check constraint
    op.create_check_constraint(
        'check_status_type',
        'transactions',
        sa.column('status').in_(['review_required', 'accepted', 'rejected', 'NOT PARSED'])
    )

    # 4. Drop enum type
    transaction_status_enum = postgresql.ENUM('parsed', 'review_needed', 'corrected', 'invalidated', name='transaction_status_enum')
    transaction_status_enum.drop(op.get_bind(), checkfirst=True)
