import csv 
import io
from typing import Iterable, Generator, List
from app.models.transactions import Transactions

def generate_transaction_csv_rows(transactions: Iterable[Transactions], headers:List[str]) -> Generator[str, None, None]:
    """
    Generate CSV rows from transactions.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(headers)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for txn in transactions:

        raw_msg = txn.raw_message
        sender = raw_msg.sender if raw_msg else None
        
        row = [
            txn.id, 
            float(txn.amount) if txn.amount is not None else "",
            txn.currency or "",
            txn.remarks or "",
            txn.status.value if txn.status else "",
            txn.txn_date.isoformat() if txn.txn_date else "",
            txn.created_at.isoformat() if txn.created_at else "",
            sender.id if sender else "",
            sender.displayname if sender else "",
            sender.phone if sender else "",
            raw_msg.message_id if raw_msg else "",
            raw_msg.raw_text if raw_msg else "",
            raw_msg.received_at.isoformat() if raw_msg and raw_msg.received_at else "",
        ]

        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
