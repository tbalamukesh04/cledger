import 'package:dio/dio.dart';
import 'api_config.dart';

class ApiService {
    late final Dio _dio;

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
    }

    Dio get client => _dio;
}