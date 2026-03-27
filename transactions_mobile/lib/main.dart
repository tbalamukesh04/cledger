import 'package:flutter/material.dart';
import 'screens/transaction_list_screen.dart';

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
      home: TransactionListScreen(),
    );
  }
}