import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'screens/transaction_list_screen.dart';
import 'models/transaction.dart';
import 'models/participant.dart';
import 'models/message_metadata.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  
  // Register Hive Adapters
  Hive.registerAdapter(TransactionAdapter());
  Hive.registerAdapter(ParticipantAdapter());
  Hive.registerAdapter(MessageMetadataAdapter());
  
  // Open Hive Boxes
  await Hive.openBox<Transaction>('transactions');
  
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Transactions',
      debugShowCheckedModeBanner: false,
      home: TransactionListScreen(),
    );
  }
}