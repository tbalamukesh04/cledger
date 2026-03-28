import '../models/transaction.dart';
import '../services/api_client.dart';

class TransactionRepository {
  final ApiClient apiClient;

  TransactionRepository({required this.apiClient});

  Future<List<Transaction>> fetchTransactions({int limit = 50, int offset = 0}) async {
    final rawList = await apiClient.getTransactions(limit: limit, offset: offset);

    return rawList
        .map((json) => Transaction.fromJson(json as Map<String, dynamic>))
        .toList();
  }

  Future<Transaction> fetchTransaction(int id) async {
    final rawData = await apiClient.getTransaction(id.toString());

    final Map<String, dynamic> transactionData = rawData['transaction'] ?? rawData;

    return Transaction.fromJson(transactionData);
  }

Future<Transaction> reviewTransaction(int id, String action, {Map<String, dynamic>? correctedFields, String? reason}) async {
    final payload = <String, dynamic>{
      'action': action,
    };
    
    if (correctedFields != null && correctedFields.isNotEmpty) {
      payload['corrected_fields'] = correctedFields;
    }

    if (reason != null && reason.trim().isNotEmpty) {
      payload['reason'] = reason.trim();
    }

    print("--> [Repository] Executing POST request...");
    
    // ⚠️ THIS IS THE CRITICAL LINE THAT WAS LIKELY MISSING ⚠️
    await apiClient.reviewTransaction(id.toString(), payload);
    
    print("--> [Repository] POST successful! Fetching fresh data via GET...");
    
    // Fetch and return the updated transaction from the backend
    return fetchTransaction(id);
  }
}