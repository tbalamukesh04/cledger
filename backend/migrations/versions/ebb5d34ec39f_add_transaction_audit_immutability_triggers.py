"""Add immutability triggers to transaction_audit table

Revision ID: ebb5d34ec39f
Revises: 26aea3793024
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'ebb5d34ec39f'
down_revision: Union[str, Sequence[str], None] = '26aea3793024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the trigger function that blocks all mutations
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_audit_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'Audit records are immutable. Operation "%" on transaction_audit is not permitted.',
                TG_OP
            USING ERRCODE = 'P0001';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Attach BEFORE UPDATE trigger
    op.execute("""
        CREATE TRIGGER trg_audit_no_update
        BEFORE UPDATE ON transaction_audit
        FOR EACH ROW
        EXECUTE FUNCTION enforce_audit_immutability();
    """)

    # Attach BEFORE DELETE trigger
    op.execute("""
        CREATE TRIGGER trg_audit_no_delete
        BEFORE DELETE ON transaction_audit
        FOR EACH ROW
        EXECUTE FUNCTION enforce_audit_immutability();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_update ON transaction_audit;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete ON transaction_audit;")
    op.execute("DROP FUNCTION IF EXISTS enforce_audit_immutability();")
