import '../models/transaction.dart';
import '../services/api_client.dart';
import '../storage/cache_service.dart';

class TransactionRepository {
  final ApiClient apiClient;
  final CacheService cacheService = CacheService();

  TransactionRepository({required this.apiClient});

  // Retrieves data from cache instantly (useful for Cache-First UI loading)
  List<Transaction> getCachedTransactions() {
    return cacheService.getTransactions();
  }

Future<List<Transaction>> fetchTransactions({int limit = 50, int offset = 0}) async {
    try {
      await Future.delayed(const Duration(seconds: 3)); // Simulated latency
      return await syncTransactions(limit: limit, offset: offset);
    } catch (e) {
      print("--> [Repository] Network fetch failed. Falling back to cache: $e");
      
      final cachedTransactions = cacheService.getTransactions();
      
      // Handle basic pagination for cached data
      if (offset >= cachedTransactions.length) return [];
      final end = (offset + limit < cachedTransactions.length) 
          ? offset + limit 
          : cachedTransactions.length;
          
      return cachedTransactions.sublist(offset, end);
    }
  }

  /// Dedicated sync method: Fetches fresh data from API and instantly updates the cache
  Future<List<Transaction>> syncTransactions({int limit = 50, int offset = 0}) async {
    print("--> [Repository] Executing background sync from API...");
    final rawList = await apiClient.getTransactions(limit: limit, offset: offset);

    final transactions = rawList
        .map((json) => Transaction.fromJson(json as Map<String, dynamic>))
        .toList();
        
    // Save fresh data to local cache overriding old entries
    await cacheService.saveTransactions(transactions);
    
    return transactions;
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
    
    await apiClient.reviewTransaction(id.toString(), payload);
    
    print("--> [Repository] POST successful! Fetching fresh data via GET...");
    
    return fetchTransaction(id);
  }
}