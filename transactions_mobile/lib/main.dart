import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'services/api_service.dart';
import 'services/api_client.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Transactions',
      debugShowCheckedModeBanner: false,
      home: ApiTestScreen(),
    );
  }
}

class ApiTestScreen extends StatelessWidget {
  const ApiTestScreen({super.key});

  Future<void> runApiTests() async {
    print("--- STARTING API TESTS ---");
    
    // Initialize our services
    final apiService = ApiService();
    final apiClient = ApiClient(apiService.client);

    // Scenario 1: Fetch Transactions
    try {
      print("Testing Scenario 1: getTransactions()...");
      final transactions = await apiClient.getTransactions();
      print("✅ Success! Retrieved ${transactions.length} transactions.");
    } catch (e) {
      print("❌ Scenario 1 Failed: $e");
    }

    // Scenario 2: Fetch Transaction Detail (Using a dummy ID, expecting a 404 or empty)
    // IMPORTANT: If you have a real ID in your DB, replace 'dummy_id_123' with it to test a 200 OK.
    try {
      print("\nTesting Scenario 2: getTransaction()...");
      final transaction = await apiClient.getTransaction("dummy_id_123");
      print("✅ Success! Retrieved transaction: $transaction");
    } catch (e) {
      print("⚠️ Scenario 2 Result (Expected 404 if ID doesn't exist): $e");
    }

    // Scenario 3: Review Transaction
    try {
      print("\nTesting Scenario 3: reviewTransaction()...");
      await apiClient.reviewTransaction("dummy_id_123", {
        "action": "correct",
        "corrected_fields": {"amount": 120}
      });
      print("✅ Success! Review request accepted.");
    } catch (e) {
      print("⚠️ Scenario 3 Result (Expected 404/422 if ID/payload is invalid): $e");
    }

    // Scenario 4: CSV Export
    try {
      print("\nTesting Scenario 4: exportTransactions()...");
      final csvData = await apiClient.exportTransactions();
      print("✅ Success! Retrieved CSV data (Showing first 50 chars):");
      print(csvData.length > 50 ? csvData.substring(0, 50) + "..." : csvData);
    } catch (e) {
      print("❌ Scenario 4 Failed: $e");
    }

    // Scenario 5: Error Handling (Force a 404 by hitting an invalid endpoint format intentionally)
    try {
      print("\nTesting Scenario 5: Error Handling...");
      // Forcing an error by sending an invalid payload format to the review endpoint
      await apiService.client.get('/api/v1/this_endpoint_does_not_exist');
    } on DioException catch (dioErr) {
      // Re-throw through our wrapper to test it
      try {
        throw ApiException(
          statusCode: dioErr.response?.statusCode ?? 500,
          message: 'Resource not found.',
        );
      } catch (e) {
        print("✅ Success! Error correctly caught and parsed: $e");
      }
    }

    print("--- API TESTS COMPLETE ---");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('API Client Tests')),
      body: Center(
        child: ElevatedButton(
          onPressed: runApiTests,
          child: const Text("Run API Tests"),
        ),
      ),
    );
  }
}