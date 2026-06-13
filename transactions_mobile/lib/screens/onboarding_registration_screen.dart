import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../widgets/whatsapp_connection_card.dart';
import 'transaction_list_screen.dart';

class OnboardingRegistrationScreen extends StatelessWidget {
  const OnboardingRegistrationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Workspace Provisioning',
          style: GoogleFonts.poppins(fontWeight: FontWeight.w600),
        ),
        elevation: 0,
        centerTitle: true,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(20.0),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16.0),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.04),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Column(
                  children: [
                    const Icon(
                      Icons.account_balance_wallet_outlined,
                      size: 64,
                      color: Color(0xFF0F9D88),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Welcome to Cledger',
                      style: GoogleFonts.poppins(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: const Color(0xFF0B2A2A),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Automate your business tracking fields directly from conversational threads.',
                      textAlign: TextAlign.center,
                      style: GoogleFonts.inter(
                        fontSize: 14,
                        color: Colors.grey[600],
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'CHANNEL INTEGRATION REQUIRED',
                style: GoogleFonts.inter(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: Colors.grey[500],
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 8),
              
              // Embed the newly created Day 100 Connection Card control surface directly inline
              const WhatsAppConnectionCard(),
              
              const SizedBox(height: 48),
              
              // Dashboard Navigation Action
              SizedBox(
                height: 54,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF0B2A2A),
                    foregroundColor: Colors.white,
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  onPressed: () {
                    Navigator.of(context).pushReplacement(
                      MaterialPageRoute(
                        builder: (context) => const TransactionListScreen(),
                      ),
                    );
                  },
                  child: Text(
                    'Continue to Dashboard',
                    style: GoogleFonts.poppins(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}