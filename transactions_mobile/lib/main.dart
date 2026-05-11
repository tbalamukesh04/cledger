import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
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
    return MaterialApp(
      title: 'Cledger',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF1F7F6), // Surface
        colorScheme: const ColorScheme.light(
          primary: Color(0xFF0F9D88), // Primary Teal
          secondary: Color(0xFFFF9F43), // Orange Accent
          surface: Color(0xFFF1F7F6), // Surface
          onSurface: Color(0xFF0B2A2A), // Text Default
        ),
        textTheme: TextTheme(
          displayLarge: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          displayMedium: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          displaySmall: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          headlineLarge: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          headlineMedium: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          headlineSmall: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          titleLarge: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          titleMedium: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          titleSmall: GoogleFonts.poppins(color: const Color(0xFF0B2A2A)),
          bodyLarge: GoogleFonts.inter(color: const Color(0xFF0B2A2A)),
          bodyMedium: GoogleFonts.inter(color: const Color(0xFF0B2A2A)),
          bodySmall: GoogleFonts.inter(color: const Color(0xFF0B2A2A)),
          labelLarge: GoogleFonts.inter(color: const Color(0xFF0B2A2A)),
          labelMedium: GoogleFonts.inter(color: const Color(0xFF0B2A2A)),
          labelSmall: GoogleFonts.inter(color: const Color(0xFF0B2A2A)),
        ),
        appBarTheme: AppBarTheme(
          backgroundColor: const Color(0xFF0F9D88),
          foregroundColor: Colors.white,
          titleTextStyle: GoogleFonts.poppins(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: Color(0xFF0F9D88),
          foregroundColor: Colors.white,
        ),
      ),
      home: const TransactionListScreen(),
    );
  }
}