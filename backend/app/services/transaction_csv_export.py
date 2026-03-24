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
        participant_info = ""
        if txn.raw_message and txn.raw_message.sender:
            sender = txn.raw_message.sender
            name = sender.displayname or ""
            participant_info = f"{name} ({sender.phone})".strip() if name else sender.phone
        
        row = [
            txn.id,
            float(txn.amount) if txn.amount is not None else "",
            txn.currency or "",
            txn.remarks or "",
            txn.status.value if txn.status else "",
            participant_info,
            txn.txn_date.isoformat() if txn.txn_date else "",
            txn.created_at.isoformat() if txn.created_at else "",
        ]

        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
