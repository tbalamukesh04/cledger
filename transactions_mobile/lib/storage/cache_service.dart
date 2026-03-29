import 'package:hive/hive.dart';
import '../models/transaction.dart';

class CacheService {
  static const String _boxName = 'transactions';

  // Retrieve the already opened box
  Box<Transaction> get _box => Hive.box<Transaction>(_boxName);

  Future<void> saveTransactions(List<Transaction> transactions) async {
    // Convert the list into a map with the transaction ID as the key
    // This ensures updates overwrite existing items instead of duplicating
    final Map<int, Transaction> transactionsMap = {
      for (var txn in transactions) txn.id: txn
    };
    
    await _box.putAll(transactionsMap);
  }

  List<Transaction> getTransactions() {
    final transactions = _box.values.toList();
    
    // Sort transactions by date descending (newest first)
    transactions.sort((a, b) {
      final dateA = a.txnDate ?? a.createdAt;
      final dateB = b.txnDate ?? b.createdAt;
      return dateB.compareTo(dateA);
    });
    
    return transactions;
  }

  Future<void> clearTransactions() async {
    await _box.clear();
  }
}