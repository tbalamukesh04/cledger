import 'package:dio/dio.dart';
import 'api_config.dart';

/// A custom exception class to handle standardized API errors from the backend.
class ApiException implements Exception {
  final int statusCode;
  final String message;
  final dynamic data;

  ApiException({required this.statusCode, required this.message, this.data});

  @override
  String toString() => 'ApiException [$statusCode]: $message';
}

class ApiService {
  late final Dio _dio;
  String? _authToken; // Centrally holds the JWT token

  ApiService() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));

    // Standardize request execution: Attach JWT dynamically if available
    // Note: Because this interceptor is on the base client, it successfully 
    // patches the context loss bug seen in Day 54's dio.download() operations.
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_authToken != null && _authToken!.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $_authToken';
        }
        return handler.next(options);
      },
    ));
  }

  /// Update the active authentication token
  void setAuthToken(String token) {
    _authToken = token;
  }

  Dio get client => _dio;

  /// Centralized GET request
  Future<dynamic> get(String endpoint, {Map<String, dynamic>? queryParameters}) async {
    return _request(() => _dio.get(endpoint, queryParameters: queryParameters));
  }

  /// Centralized POST request
  Future<dynamic> post(String endpoint, {dynamic data, Map<String, dynamic>? queryParameters}) async {
    return _request(() => _dio.post(endpoint, data: data, queryParameters: queryParameters));
  }

  /// Centralized PUT request
  Future<dynamic> put(String endpoint, {dynamic data, Map<String, dynamic>? queryParameters}) async {
    return _request(() => _dio.put(endpoint, data: data, queryParameters: queryParameters));
  }

  /// Centralized DELETE request
  Future<dynamic> delete(String endpoint, {dynamic data, Map<String, dynamic>? queryParameters}) async {
    return _request(() => _dio.delete(endpoint, data: data, queryParameters: queryParameters));
  }

  /// Internal request wrapper for standardized success parsing and error handling
  Future<dynamic> _request(Future<Response> Function() requestFunc) async {
    try {
      final response = await requestFunc();
      return _normalizeResponse(response.data);
    } on DioException catch (e) {
      _handleDioError(e);
      rethrow; // Safety fallback, _handleDioError always throws ApiException
    } catch (e) {
      throw ApiException(
        statusCode: 500,
        message: 'Unexpected application error: $e',
      );
    }
  }

  /// Standardize success parsing by flattening backend pagination wrappers
  dynamic _normalizeResponse(dynamic data) {
    if (data is Map<String, dynamic>) {
      if (data.containsKey('transactions')) return data['transactions'];
      if (data.containsKey('items')) return data['items'];
      if (data.containsKey('data')) return data['data'];
    }
    return data;
  }

  void _handleDioError(DioException e) {
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
        case 413:
          errorMessage = backendMessage ?? 'Payload too large.';
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
  }
}