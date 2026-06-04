enum Environment { dev, production }

class ApiConfig {
  // Enforce configuration strictly through --dart-define.
  // No default values, no fallbacks, no silent assumptions.
  static const String _baseUrl = String.fromEnvironment('API_BASE_URL');
  static const String _environmentStr = String.fromEnvironment('ENVIRONMENT');

  static String get baseUrl {
    if (_baseUrl.isEmpty) {
      throw Exception(
          'FATAL: API_BASE_URL is missing. Compile with --dart-define=API_BASE_URL=http://<your-endpoint>');
    }
    
    // if (currentEnvironment == Environment.production && !_baseUrl.startsWith('https://')) {
    //   throw Exception(
    //       'FATAL: Network Security Exception. API_BASE_URL must strictly use HTTPS in production.');
    // }
    return _baseUrl;
  }

  static Environment get currentEnvironment {
    if (_environmentStr.isEmpty) {
      throw Exception(
          'FATAL: ENVIRONMENT is missing. Compile with --dart-define=ENVIRONMENT=dev or --dart-define=ENVIRONMENT=production');
    }
    
    switch (_environmentStr.toLowerCase()) {
      case 'dev':
      case 'development':
        return Environment.dev;
      case 'prod':
      case 'production':
        return Environment.production;
      default:
        throw Exception(
            'FATAL: Invalid ENVIRONMENT value "$_environmentStr". Must be "dev" or "production".');
    }
  }

  // Helper getters to control logging verbosity, debug UI, and analytics downstream
  static bool get isProduction => currentEnvironment == Environment.production;
  static bool get isDevelopment => currentEnvironment == Environment.dev;
}