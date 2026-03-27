import 'package:dio/dio.dart';

/// A custom exception class to handle standardized API errors from the backend (Phase 7).
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
  Future<List<dynamic>> getTransactions() async {
    final response = await request(
      '/api/v1/transactions/', // Matches the Phase 7 backend router prefix
      method: 'GET',
    );
    
    // Safely extract the list depending on if the backend returns a raw array 
    // or wraps it in a paginated dictionary (e.g., {'items': [...]})
    if (response is List) {
      return response;
    } else if (response is Map<String, dynamic>) {
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
  /// Returns the raw CSV data as a String (file saving to be implemented later).
  Future<String> exportTransactions() async {
    final response = await request(
      '/api/v1/transactions/export',
      method: 'GET',
    );
    
    // Dio automatically parses text/csv into a string
    return response.toString();
  }

  /// Base HTTP request wrapper
  /// Handles methods, JSON decoding (automatic in Dio), and standardized error parsing.
  Future<dynamic> request(
    String endpoint, {
    String method = 'GET',
    Map<String, dynamic>? data,
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      // Execute the request. Headers (Content-Type) are already attached via ApiService.
      final response = await _client.request(
        endpoint,
        data: data,
        queryParameters: queryParameters,
        options: Options(method: method),
      );
      
      // 2xx responses (Success). Dio automatically decodes the JSON payload.
      return response.data;

    } on DioException catch (e) {
      // Handle HTTP errors specifically aligning with UI requirements
      if (e.response != null) {
        final statusCode = e.response!.statusCode ?? 500;
        final responseData = e.response!.data;
        
        // 1. Try to extract the standardized error from Phase 7 backend schema
        String? backendMessage;
        if (responseData is Map<String, dynamic>) {
           backendMessage = responseData['detail']?.toString() ?? 
                            responseData['message']?.toString();
        }

        // 2. Map status codes to readable messages for UI handling (Fallback)
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
        // Network errors, timeouts, or connection refused
        throw ApiException(
          statusCode: 500,
          message: 'Network error or timeout: Please check your internet connection.',
        );
      }
    } catch (e) {
      // Fallback for any other unexpected Dart errors
      throw ApiException(
        statusCode: 500,
        message: 'Unexpected application error: $e',
      );
    }
  }
}