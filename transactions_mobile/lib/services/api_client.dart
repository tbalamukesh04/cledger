import 'package:dio/dio.dart';

/// A custom exception class to handle standardized API errors from the backend.
class ApiException implements Exception {
  final int statusCode;
  final String message;
  final dynamic data;

  ApiException({required this.statusCode, required this.message, this.data});

  @override
  String toString() => 'ApiException [$statusCode]: $message';
}

class ApiClient {
  final Dio _client;

  ApiClient(this._client);

  /// Retrieves a list of transactions from the backend.
  Future<List<dynamic>> getTransactions({int limit = 50, int offset = 0}) async {
    final response = await request(
      '/api/v1/transactions/', // Matches the Phase 7 backend router prefix
      method: 'GET',
      queryParameters: {
        'limit': limit,
        'offset': offset,
      },
    );
    
    // Safely extract the list depending on if the backend returns a raw array 
    // or wraps it in a paginated dictionary (e.g., {'transactions': [...]})
    if (response is List) {
      return response;
    } else if (response is Map<String, dynamic>) {
      if (response.containsKey('transactions')) return response['transactions'] as List<dynamic>;
      if (response.containsKey('items')) return response['items'] as List<dynamic>;
      if (response.containsKey('data')) return response['data'] as List<dynamic>;
    }
    
    return [];
  }

  /// Retrieves the details of a single transaction by ID.
  Future<dynamic> getTransaction(String id) async {
    final response = await request(
      '/api/v1/transactions/$id',
      method: 'GET',
    );
    
    return response;
  }

  /// Submits a review (correction or invalidation) for a specific transaction.
  Future<void> reviewTransaction(String id, Map<String, dynamic> payload) async {
    await request(
      '/api/v1/transactions/$id/review',
      method: 'POST',
      data: payload,
    );
  }

  /// Triggers a CSV export of the transactions.
  Future<String> exportTransactions() async {
    final response = await request(
      '/api/v1/transactions/export',
      method: 'GET',
    );
    
    return response.toString();
  }

  /// Base HTTP request wrapper
  Future<dynamic> request(
    String endpoint, {
    String method = 'GET',
    Map<String, dynamic>? data,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final response = await _client.request(
        endpoint,
        data: data,
        queryParameters: queryParameters,
        options: Options(method: method),
      );
      
      return response.data;

    } on DioException catch (e) {
      if (e.response != null) {
        final statusCode = e.response!.statusCode ?? 500;
        final responseData = e.response!.data;
        
        String? backendMessage;
        if (responseData is Map<String, dynamic>) {
           backendMessage = responseData['detail']?.toString() ?? 
                            responseData['message']?.toString();
        }

        String errorMessage;
        switch (statusCode) {
          case 400:
            errorMessage = backendMessage ?? 'Client error: Invalid request parameters.';
            break;
          case 401:
            errorMessage = backendMessage ?? 'Authentication error: Unauthorized access.';
            break;
          case 404:
            errorMessage = backendMessage ?? 'Resource not found.';
            break;
          case 429:
            errorMessage = backendMessage ?? 'Rate limit exceeded: Too many requests. Please try again later.';
            break;
          case 500:
          default:
            errorMessage = backendMessage ?? 'Server error: API request failed with status $statusCode.';
            break;
        }

        throw ApiException(
          statusCode: statusCode,
          message: errorMessage,
          data: responseData,
        );
      } else {
        throw ApiException(
          statusCode: 500,
          message: 'Network error or timeout: Please check your internet connection.',
        );
      }
    } catch (e) {
      throw ApiException(
        statusCode: 500,
        message: 'Unexpected application error: $e',
      );
    }
  }
}