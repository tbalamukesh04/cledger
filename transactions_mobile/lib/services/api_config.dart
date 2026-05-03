class ApiConfig {
    // Base URL for the backend API.
    // IMPORTANT: If running on an android emulator, change 'localhost' to '10.2.2.2'
    // to successfully connect to your local computer's backend. 
    // static const String baseUrl = "http://10.0.2.2:8000";
    static const String baseUrl = String.fromEnvironment(
        'API_BASE_URL',
        defaultValue: 'http://localhost:8000',
    );
}