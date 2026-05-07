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
      print("--> [Repository] Fetching MORE transactions from API (limit: $limit, offset: $offset)...");
      // ApiClient now handles parsing and schema validation internally
      final transactions = await apiClient.getTransactions(limit: limit, offset: offset);
          
      // Merge paginated data into the local cache rather than overwriting
      if (transactions.isNotEmpty) {
        final existingCache = cacheService.getTransactions();
        final Map<int, Transaction> cacheMap = {
          for (var t in existingCache) t.id: t
        };
        for (var t in transactions) {
          cacheMap[t.id] = t;
        }
        await cacheService.saveTransactions(cacheMap.values.toList());
      }
          
      return transactions;
    } catch (e) {
      print("--> [Repository] Network fetch failed. Falling back to cache: $e");
      
      final cachedTransactions = cacheService.getTransactions();
      
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
    final transactions = await apiClient.getTransactions(limit: limit, offset: offset);
        
    // Save fresh data to local cache overriding old entries
    await cacheService.saveTransactions(transactions);
    
    return transactions;
  }

  Future<Transaction> fetchTransaction(int id) async {
    // ApiClient now handles parsing and schema validation internally
    final transaction = await apiClient.getTransactionById(id.toString());
    
    // Sync this individual transaction into the local cache
    try {
      final existingCache = cacheService.getTransactions();
      final index = existingCache.indexWhere((t) => t.id == id);
      if (index != -1) {
        existingCache[index] = transaction;
        await cacheService.saveTransactions(existingCache);
      }
    } catch (e) {
      print("--> [Repository] Non-fatal error updating cache for single transaction: $e");
    }

    return transaction;
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

    // 1. Optimistic Update (Update local cache instantly)
    final existingCache = cacheService.getTransactions();
    final index = existingCache.indexWhere((t) => t.id == id);
    Transaction? backupTxn;
    
    if (index != -1) {
      backupTxn = existingCache[index];
      try {
        final jsonMap = backupTxn.toJson();
        
        if (action == 'correct') {
          jsonMap['status'] = 'CORRECTED';
          if (correctedFields != null) {
            correctedFields.forEach((key, value) {
              jsonMap[key] = value;
            });
          }
        } else if (action == 'invalidate') {
          jsonMap['status'] = 'INVALIDATED';
          if (reason != null && reason.trim().isNotEmpty) {
            final oldRemarks = jsonMap['remarks'] ?? '';
            jsonMap['remarks'] = oldRemarks.toString().isEmpty ? reason.trim() : '$oldRemarks | Invalidation Reason: ${reason.trim()}';
          }
        }
        
        final optimisticTxn = Transaction.fromJson(jsonMap);
        existingCache[index] = optimisticTxn;
        await cacheService.saveTransactions(existingCache);
        print("--> [Repository] Optimistic cache update applied for $action.");
      } catch (e) {
        print("--> [Repository] Failed to apply optimistic update: $e");
      }
    }

    // 2. Network Request
    try {
      print("--> [Repository] Executing POST request...");
      await apiClient.reviewTransaction(id.toString(), payload);
      print("--> [Repository] POST successful! Fetching fresh data via GET...");
      
      // Fetching the fresh transaction will auto-sync with the cache inside fetchTransaction()
      return await fetchTransaction(id);
    } catch (e) {
      // 3. Rollback on Failure
      print("--> [Repository] Network request failed! Rolling back optimistic update...");
      if (backupTxn != null) {
        final revertCache = cacheService.getTransactions();
        final revertIndex = revertCache.indexWhere((t) => t.id == id);
        if (revertIndex != -1) {
          revertCache[revertIndex] = backupTxn;
          await cacheService.saveTransactions(revertCache);
        }
      }
      rethrow; // Rethrow to surface the error in the UI (e.g., Snackbar)
    }
  }

  /// Local-only create flow: collects input, stores in local cache,
  /// marks as pending_local. No API call made in this phase.
  Future<Transaction> createTransaction(Transaction transaction) async {
    print("--> [Repository] Creating local-only transaction...");
    
    final existingCache = cacheService.getTransactions();
    
    try {
      final jsonMap = transaction.toJson();
      
      // Assign a temporary negative local ID to avoid collisions with real DB IDs
      if (jsonMap['id'] == null || jsonMap['id'] == 0) {
        jsonMap['id'] = -DateTime.now().millisecondsSinceEpoch; 
      }
      
      // Force status to identify as a locally created offline item
      jsonMap['status'] = 'PENDING_LOCAL';
      
      final localTxn = Transaction.fromJson(jsonMap);
      
      // Insert at the top of the cache list
      existingCache.insert(0, localTxn);
      await cacheService.saveTransactions(existingCache);
      
      print("--> [Repository] Local transaction saved to cache with ID: ${localTxn.id}");
      return localTxn;
      
    } catch (e) {
      print("--> [Repository] Critical error during local creation: $e");
      // Ensure the error bubbles up so the UI can show the SnackBar
      rethrow; 
    }
  }
}