import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'services/api_service.dart';
import 'services/api_client.dart';
import 'models/transaction.dart';
import 'repositories/transaction_repository.dart';

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

Future<void> runEndToEndTests() async {
    print("--- STARTING DAY 48 END-TO-END TESTS ---");
    
    // Initialize our dependencies
    final apiService = ApiService();

    final testToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJ0ZW5hbnRfaWQiOjEsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc3NDU1OTI5N30.QpuvpQa7oG8axwIGR85VF_kG-vcYafCtypA5nCem7wQ";
    apiService.client.options.headers['Authorization'] = 'Bearer $testToken';
    
    apiService.client.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        options.headers['Authorization'] = 'Bearer $testToken';
        return handler.next(options);
      },
    ));

    final apiClient = ApiClient(apiService.client);
    final repository = TransactionRepository(apiClient: apiClient);

    try {
      // Scenario 1: Fetch Transactions
      print("\n▶ Testing Scenario 1: Fetch Transactions...");
      final transactions = await repository.fetchTransactions();
      print("✅ Success! Retrieved ${transactions.length} typed Transaction objects.");
      
      if (transactions.isNotEmpty) {
        final firstTxn = transactions.first;
        
        // Scenario 2: Nested Object Parsing
        print("\n▶ Testing Scenario 2: Nested Object Parsing...");
        print("   - Base Amount: ${firstTxn.amount} ${firstTxn.currency}");
        if (firstTxn.participant != null) {
          print("   ✅ Participant correctly populated: ${firstTxn.participant?.name ?? firstTxn.participant?.phone}");
        } else {
          print("   ⚠️ No Participant data in this transaction.");
        }
        if (firstTxn.messageMetadata != null) {
          print("   ✅ MessageMetadata correctly populated: '${firstTxn.messageMetadata?.text}'");
        } else {
          print("   ⚠️ No MessageMetadata in this transaction.");
        }

        // Scenario 3: Transaction Detail Retrieval
        print("\n▶ Testing Scenario 3: Transaction Detail Retrieval...");
        final detailedTxn = await repository.fetchTransaction(firstTxn.id.toString());
        print("✅ Success! Retrieved full detail for Transaction ID: ${detailedTxn.id}");

        // Scenario 4: Serialization Integrity
        print("\n▶ Testing Scenario 4: Serialization Integrity...");
        final serializedJson = detailedTxn.toJson();
        print("✅ Serialized JSON successfully! Contains ID: ${serializedJson['id']} and Amount: ${serializedJson['amount']}");
        
        // Final sanity check - parse serialized map back to object to prove perfectly mapped loop
        final roundTripTxn = Transaction.fromJson(serializedJson);
        print("✅ Round-trip parsing successful. ID matches: ${roundTripTxn.id == detailedTxn.id}");

      } else {
        print("⚠️ No transactions returned from backend. Insert data to fully test nested parsing.");
      }
      
    } catch (e, stackTrace) {
      print("❌ Test Failed: $e");
      print(stackTrace);
    }
    
    print("--- END-TO-END TESTS COMPLETE ---");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('API Repository Tests')),
      body: Center(
        child: ElevatedButton(
          onPressed: runEndToEndTests,
          child: const Text("Run E2E Repository Tests"),
        ),
      ),
    );
  }
}