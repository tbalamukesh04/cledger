import csv 
import io
from typing import Iterable, Generator, List
from app.models.transactions import Transactions

def generate_transaction_csv_rows(transactions: Iterable[Transactions], headers:List[str]) -> Generator[str, None, None]:
    """
    Generate CSV rows from transactions.
    Yields in larger chunks to optimize ASGI throughput and completely bypass middleware buffering delays.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(headers)
    # CRITICAL: Yield the headers immediately so the HTTP stream begins instantly
    # before the database starts its query execution!
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    
    count = 0