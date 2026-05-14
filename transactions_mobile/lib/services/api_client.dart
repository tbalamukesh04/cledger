import 'package:dio/dio.dart';
import '../models/transaction.dart';
import '../models/update_metadata.dart';
import 'api_service.dart';

class ApiClient {
  final ApiService _apiService;

  ApiClient(this._apiService);

  /// Retrieves a list of transactions from the backend and parses them into models.
  Future<List<Transaction>> getTransactions({int limit = 50, int offset = 0}) async {
    final data = await _apiService.get(
      '/api/v1/transactions/',
      queryParameters: {
        'limit': limit,
        'offset': offset,
      },
    );
    
    if (data is List) {
      return data.map((json) => Transaction.fromJson(json as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// Retrieves the details of a single transaction by ID.
  Future<Transaction> getTransactionById(String id) async {
    final data = await _apiService.get('/api/v1/transactions/$id');
    
    // Support both wrapped {'transaction': {...}} and flat responses
    final Map<String, dynamic> transactionData = 
        (data is Map<String, dynamic> && data.containsKey('transaction')) 
            ? data['transaction'] 
            : data as Map<String, dynamic>;
            
    return Transaction.fromJson(transactionData);
  }

  /// Placeholder for future direct transaction creation. 
  /// Currently, transactions are primarily ingested via Webhooks.
  Future<Transaction> createTransaction(Map<String, dynamic> payload) async {
    final data = await _apiService.post('/api/v1/transactions/', data: payload);
    return Transaction.fromJson(data as Map<String, dynamic>);
  }

  /// Placeholder for direct transaction updates.
  Future<Transaction> updateTransaction(String id, Map<String, dynamic> payload) async {
    final data = await _apiService.put('/api/v1/transactions/$id', data: payload);
    return Transaction.fromJson(data as Map<String, dynamic>);
  }

  /// Submits a review (correction or invalidation) for a specific transaction.
  Future<void> reviewTransaction(String id, Map<String, dynamic> payload) async {
    await _apiService.post(
      '/api/v1/transactions/$id/review',
      data: payload,
    );
  }

 /// Triggers a CSV export of the transactions.
  Future<void> exportTransactions(String savePath) async {
    try {
      // client.download is executed natively by Dio, skipping _request to handle 
      // the file stream, but it still automatically inherits the Auth Interceptor
      await _apiService.client.download(
        '/api/v1/transactions/export',
        savePath,
      );
    } on DioException catch (e) {
      final statusCode = e.response?.statusCode ?? 500;
      
      // Specifically handle the Phase 7 413 Payload Too Large boundary
      if (statusCode == 413) {
        throw ApiException(
          statusCode: 413,
          message: 'Export too large. Please contact support or try a smaller dataset.',
          data: e.response?.data,
        );
      }
      
      throw ApiException(
        statusCode: statusCode,
        message: 'Failed to download export: ${e.message}',
        data: e.response?.data,
      );
    }
  }

  /// Fetches the application update metadata to verify client version constraints.
  Future<UpdateMetadata> fetchLatestAppVersion() async {
    final data = await _apiService.get('/api/v1/app/version');
    
    // Flatten any unnecessary wrapping payload structures safely
    final Map<String, dynamic> metadataPayload = 
        (data is Map<String, dynamic> && data.containsKey('metadata'))
            ? data['metadata']
            : data as Map<String, dynamic>;

    return UpdateMetadata.fromJson(metadataPayload);
  }
}