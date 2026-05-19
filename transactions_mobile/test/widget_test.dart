import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:transactions_mobile/main.dart';
import 'package:transactions_mobile/models/transaction.dart';
import 'package:transactions_mobile/models/participant.dart';
import 'package:transactions_mobile/models/message_metadata.dart';

// Helper to allow real-time network retries (dio_smart_retry) to process 
// while advancing the Flutter UI frame clock past infinite loading spinners.
Future<void> pumpUntilFound(WidgetTester tester, Finder finder, {int timeoutSeconds = 30}) async {
  int maxPumps = (timeoutSeconds * 1000) ~/ 200;
  int currentPumps = 0;
  
  while (finder.evaluate().isEmpty) {
    if (currentPumps >= maxPumps) {
      throw TestFailure('Timeout waiting for widget: ${finder.description}');
    }
    // Yield briefly to the real OS event loop to allow SocketExceptions to bubble up
    await tester.runAsync(() async {
      await Future.delayed(const Duration(milliseconds: 10));
    });
    // CRITICAL: Advance the Flutter virtual clock by 200ms per frame.
    // This forces dio_smart_retry's exponential backoff timers to execute instantly.
    await tester.pump(const Duration(milliseconds: 200));
    currentPumps++;
  }
}

class FastFailHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(context);
    // Force a 100ms timeout to bypass OS-level TCP hangs and trigger an instant offline SocketException
    client.connectionTimeout = const Duration(milliseconds: 100);
    return client;
  }
}

void main() {
  setUpAll(() async {
    // Disable runtime font fetching to prevent network-related crashes during offline tests
    GoogleFonts.config.allowRuntimeFetching = false;
    
    // Inject the fast-fail network override for instant offline simulation
    HttpOverrides.global = FastFailHttpOverrides();
    final tempDir = await Directory.systemTemp.createTemp('hive_test');
    Hive.init(tempDir.path);
    
    Hive.registerAdapter(TransactionAdapter());
    Hive.registerAdapter(ParticipantAdapter());
    Hive.registerAdapter(MessageMetadataAdapter());
  });

  setUp(() async {
    final box = await Hive.openBox<Transaction>('transactions');
    await box.clear();
    
    // Seed local cache
    final offlineTxn = Transaction(
      id: 9999,
      amount: 750.50,
      currency: 'INR',
      remarks: 'Validated offline transfer payload testing structure',
      status: 'COMPLETED',
      txnDate: DateTime(2026, 05, 19),
      createdAt: DateTime(2026, 05, 19),
      participant: Participant(id: 101, name: 'Offline Tester', phone: '+919876543210'),
      syncState: 'synced',
    );
    
    await box.put(9999, offlineTxn);
  });

  tearDown(() async {
    await Hive.box<Transaction>('transactions').close();
  });

  testWidgets('Cold Start Offline Launch loads cached transactions gracefully', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    
    // Wait for real background sync to fail and trigger the SnackBar
    await pumpUntilFound(tester, find.text('Offline: Showing cached transactions'));
    
    expect(find.text('Offline Tester'), findsOneWidget);
    expect(find.textContaining('750.50'), findsOneWidget);
    expect(find.byType(ListView), findsOneWidget);
  });

  testWidgets('Optimistic Execution maintains local cache on network failure', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    
    // Wait for initial sync failure to clear
    await pumpUntilFound(tester, find.text('Offline: Showing cached transactions'));
    
    // Wait for SnackBar to recede so taps aren't blocked by the overlay
    await tester.pump(const Duration(seconds: 5));

    // Navigate to Detail Screen
    await tester.tap(find.text('Offline Tester'));
    await pumpUntilFound(tester, find.text('Transaction #9999'));

    expect(find.text('Pending Sync'), findsNothing);
    expect(find.text('COMPLETED'), findsOneWidget);

    // Navigate to Edit Screen
    await tester.tap(find.byTooltip('Review & Edit Transaction'));
    await pumpUntilFound(tester, find.text('Correct'));

    // Trigger Optimistic Action
    await tester.tap(find.text('Correct'));

    // Wait for real POST request to fail and trigger fallback UI
    await pumpUntilFound(tester, find.text('Offline: Changes saved locally.'));
    
    // Validate Screen popped back to Detail and Optimistic UI is applied
    await pumpUntilFound(tester, find.text('Pending Sync'));
    
    expect(find.text('Transaction #9999'), findsOneWidget); 
    expect(find.text('CORRECTED'), findsOneWidget); 
  });

  testWidgets('Offline cache access navigation and detail retrieval', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    
    // Wait for boot and offline sync failure
    await pumpUntilFound(tester, find.text('Offline: Showing cached transactions'));
    
    // Wait for SnackBar to clear to avoid tap interception
    // Advance virtual clock by 5 seconds to instantly dismiss animations without pumpAndSettle
    await tester.pump(const Duration(seconds: 5));

    // Verify initial list state: no duplicate rendering, no missing records
    expect(find.text('Offline Tester'), findsOneWidget);

    // 1st Navigation to Detail View
    await tester.tap(find.text('Offline Tester'));
    await pumpUntilFound(tester, find.text('Transaction #9999'));

    // Verify cached detail retrieval
    expect(find.text('Transaction #9999'), findsOneWidget);
    expect(find.text('Validated offline transfer payload testing structure'), findsOneWidget);

    // Navigate back to list
    await tester.tap(find.byType(BackButton));
    await pumpUntilFound(tester, find.text('Offline Tester'));

    // Verify list stability after back navigation (no duplicates/missing)
    expect(find.text('Offline Tester'), findsOneWidget);

    // 2nd Navigation to Detail View (navigate repeatedly)
    await tester.tap(find.text('Offline Tester'));
    await pumpUntilFound(tester, find.text('Transaction #9999'));
    
    // Verify detail consistency
    expect(find.text('Transaction #9999'), findsOneWidget);

    // Navigate back to list again
    await tester.tap(find.byType(BackButton));
    await pumpUntilFound(tester, find.text('Offline Tester'));

    // Final verification of list stability
    expect(find.text('Offline Tester'), findsOneWidget);
  });
}