from app.models.transactions import Transactions

def serialize_transaction_snapshot(transaction: Transactions) -> dict:
    """
    Converts a Transactions ORM object to a JSON dictionary suitable for storage
    """
    return transaction.to_dict()