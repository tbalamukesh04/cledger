import 'package:flutter/material.dart';
import 'package:transactions_mobile/services/api_service.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'CLedger',
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        body: Center(
          child: Text('CLedger'),
        ),
      ),
    );
  }
}