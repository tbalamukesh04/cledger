import csv 
import io
from typing import Iterable, Generator, List
from app.models.transactions import Transactions

def generate_transaction_csv_rows(transactions: Iterable[Transactions], headers: List[str]) -> Generator[str, None, None]:
    """
    Generate CSV rows from transactions.
    Yields in larger chunks to optimize ASGI throughput and completely bypass middleware buffering delays.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # 1. Write and yield headers immediately to start the HTTP stream
    writer.writerow(headers)
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    
    count = 0
    # 2. Iterate through the actual transaction data
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
        count += 1
        
        # 3. Yield in batches of 500 rows to optimize network throughput
        if count % 500 == 0:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    # 4. Final flush for any remaining rows in the buffer
    if buffer.tell() > 0:
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)