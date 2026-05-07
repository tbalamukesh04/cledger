import '../models/transaction.dart';
import '../models/participant.dart';
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
          // Conflict Resolution: Preserve locally modified/pending items during pagination
          if (cacheMap.containsKey(t.id) && cacheMap[t.id]!.syncState == 'pending_local') {
            continue;
          }
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
    final serverTransactions = await apiClient.getTransactions(limit: limit, offset: offset);
        
    final existingCache = cacheService.getTransactions();
    final pendingLocalTxns = existingCache.where((t) => t.syncState == 'pending_local').toList();
    
    // Deduplicate by ID
    final Map<int, Transaction> serverMap = {
      for (var t in serverTransactions) t.id: t
    };
    
    // Merge with local pending_local items (preserve them)
    for (var pending in pendingLocalTxns) {
      if (serverMap.containsKey(pending.id)) {
        serverMap[pending.id] = pending;
      }
    }
    
    // Maintain ordering: pending_local items pinned on top
    final List<Transaction> finalList = [];
    final localCreations = pendingLocalTxns.where((t) => !serverMap.containsKey(t.id)).toList();
    
    final serverValues = serverMap.values.toList();
    final serverPendingEdits = serverValues.where((t) => t.syncState == 'pending_local').toList();
    final serverSynced = serverValues.where((t) => t.syncState != 'pending_local').toList();
    
    finalList.addAll(localCreations);
    finalList.addAll(serverPendingEdits);
    finalList.addAll(serverSynced);
        
    // Save merged data to local cache
    await cacheService.saveTransactions(finalList);
    
    return finalList;
  }

  Future<Transaction> fetchTransaction(int id) async {
    try {
      final transaction = await apiClient.getTransactionById(id.toString());
      
      // Conflict Resolution for single detail fetch
      final existingTxn = cacheService.getTransactionDetail(id);
      if (existingTxn != null && existingTxn.syncState == 'pending_local') {
        return existingTxn; // Preserve local offline state against overwrites
      }
      
      await cacheService.saveTransactionDetail(id, transaction);
      return transaction;
    } catch (e) {
      print("--> [Repository] Network fetch failed for detail. Falling back to cache: $e");
      final cachedTransaction = cacheService.getTransactionDetail(id);
      if (cachedTransaction != null) {
        return cachedTransaction;
      }
      rethrow;
    }
  }

  Future<Transaction> reviewTransaction(int id, String action, {Map<String, dynamic>? correctedFields, String? reason}) async {
    // 1. Optimistic Cache Update
    final cachedTxn = cacheService.getTransactionDetail(id);
    if (cachedTxn != null) {
      String newStatus = cachedTxn.status ?? '';
      if (action.toUpperCase() == 'CORRECT') newStatus = 'CORRECTED';
      else if (action.toUpperCase() == 'INVALIDATE') newStatus = 'INVALIDATED';

      final updatedTxn = Transaction(
        id: cachedTxn.id,
        rawMessageId: cachedTxn.rawMessageId,
        amount: (correctedFields != null && correctedFields.containsKey('amount')) 
            ? double.tryParse(correctedFields['amount'].toString()) ?? cachedTxn.amount 
            : cachedTxn.amount,
        currency: (correctedFields != null && correctedFields.containsKey('currency'))
            ? correctedFields['currency'] as String?
            : cachedTxn.currency,
        remarks: (correctedFields != null && correctedFields.containsKey('remarks'))
            ? correctedFields['remarks'] as String?
            : cachedTxn.remarks,
        txnDate: cachedTxn.txnDate,
        status: newStatus.isNotEmpty ? newStatus : cachedTxn.status,
        confidence: cachedTxn.confidence,
        createdAt: cachedTxn.createdAt,
        updatedAt: DateTime.now(),
        participant: cachedTxn.participant,
        messageMetadata: cachedTxn.messageMetadata,
        syncState: 'pending_local',
      );
      
      // Save the optimistic state with pending_local flag
      await cacheService.saveTransactionDetail(id, updatedTxn);
    }

    // 2. Prepare API Payload
    final payload = <String, dynamic>{
      'action': action,
    };
    
    if (correctedFields != null && correctedFields.isNotEmpty) {
      payload['corrected_fields'] = correctedFields;
    }

    if (reason != null && reason.trim().isNotEmpty) {
      payload['reason'] = reason.trim();
    }

    // 3. Execute Request
    print("--> [Repository] Executing POST request...");
    
    try {
      await apiClient.reviewTransaction(id.toString(), payload);
      print("--> [Repository] POST successful! Fetching fresh data via GET...");
      
      // Sync fresh validated data into local cache (removes pending_local)
      return await fetchTransaction(id);
    } catch (e) {
      print("--> [Repository] Network fetch failed. Keeping optimistic update in cache: $e");
      // Keep optimistic update & throw to surface the error in UI SnackBar without rollback
      throw Exception('Network failed, but your changes are saved locally. ($e)');
    }
  }

  Future<Transaction> createTransaction({
    required double amount,
    required String currency,
    required String description,
    required DateTime date,
    required String transactionType,
    required String counterparty,
  }) async {
    // Use a negative temporary ID so Hive's integer-key sorting keeps it at the top of the local cache
    final tempId = -DateTime.now().millisecondsSinceEpoch;
    
    final transaction = Transaction(
      id: tempId,
      amount: amount,
      currency: currency,
      remarks: description,
      txnDate: date,
      status: transactionType,
      createdAt: DateTime.now(),
      syncState: 'pending_local',
      participant: Participant(
        id: tempId, 
        name: counterparty, 
        phone: 'Unknown'
      ),
    );

    // Persist to Hive box (this also acts as our in-memory list state)
    await cacheService.saveTransactionDetail(tempId, transaction);

    return transaction;
  }
}