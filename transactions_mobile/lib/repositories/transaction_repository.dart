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
}