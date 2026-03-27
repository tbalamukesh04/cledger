import '../models/transaction.dart';
import '../services/api_client.dart';

class TransactionRepository {
    final ApiClient apiClient;

    TransactionRepository({required this.apiClient});

    Future<List<Transaction>> fetchTransactions() async {
        final rawList = await apiClient.getTransactions();

        return rawList
        .map((json) => Transaction.fromJson(json as Map<String, dynamic>))
        .toList();

    }
    Future<Transaction> fetchTransaction(String id) async {
        final rawData = await apiClient.getTransaction(id);

        return Transaction.fromJson(rawData as Map<String, dynamic>);
    }
}