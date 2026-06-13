import 'package:flutter/material.dart';
import 'whatsapp_registration_screen.dart'; // Assume this will be your Meta-logic screen

class RegistrationScreen extends StatelessWidget {
  const RegistrationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Setup Cledger')),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.account_balance_wallet, size: 80, color: Colors.blueAccent),
            const SizedBox(height: 24),
            const Text(
              'Welcome to Cledger',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            const Text(
              'To begin, please connect your WhatsApp Business account to sync transactions automatically.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey),
            ),
            const SizedBox(height: 32),
            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => const WhatsAppRegistrationScreen()),
                );
              },
              child: const Text('Connect WhatsApp Business'),
            ),
          ],
        ),
      ),
    );
  }
}