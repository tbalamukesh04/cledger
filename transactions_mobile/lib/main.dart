import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'screens/transaction_list_screen.dart';
import 'screens/onboarding_registration_screen.dart';
import 'models/transaction.dart';
import 'models/participant.dart';
import 'models/message_metadata.dart';
import 'services/api_service.dart';
import 'services/api_client.dart';
import 'services/version_service.dart';
import 'services/update_prompt_dialog.dart';
import 'package:app_links/app_links.dart'; 
import 'dart:async';

// Global navigation key enabling safe uncoupled context resolution from root wrappers
final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final appLinks = AppLinks();
  
  // Listen for the redirect from the Meta Wizard
  appLinks.uriLinkStream.listen((Uri? uri) {
    if (uri != null && uri.scheme == 'cledger' && uri.host == 'whatsapp') {
      print("--> [DeepLink] Callback received: $uri");
      
      // Navigate to the transaction screen upon successful WhatsApp mapping
      rootNavigatorKey.currentState?.pushReplacement(
        MaterialPageRoute(builder: (context) => const TransactionListScreen()),
      );
    }
  });

  try {
    await Hive.initFlutter();
    
    // Register Hive Adapters
    Hive.registerAdapter(TransactionAdapter());
    Hive.registerAdapter(ParticipantAdapter());
    Hive.registerAdapter(MessageMetadataAdapter());
    
    // Open Hive Boxes
    await Hive.openBox<Transaction>('transactions');
    
    runApp(const MyApp());
  } catch (e, stackTrace) {
    runApp(
      MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Text(
                'INIT FATAL ERROR:\n$e\n\nSTACKTRACE:\n$stackTrace',
                style: const TextStyle(color: Colors.red, fontSize: 14),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class UpdatePromptInterceptor extends StatefulWidget {
  final Widget child;

  const UpdatePromptInterceptor({super.key, required this.child});

  @override
  State<UpdatePromptInterceptor> createState() => _UpdatePromptInterceptorState();
}

class _UpdatePromptInterceptorState extends State<UpdatePromptInterceptor> {
  bool _isUpdateForced = false;

  @override
  void initState() {
    super.initState();
    // Schedule update verification asynchronously immediately after initial framework render
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _executeStartupUpdateCheck();
    });
  }

  Future<void> _executeStartupUpdateCheck() async {
    try {
      final apiService = ApiService();
      final apiClient = ApiClient(apiService);
      final versionService = VersionService(apiClient);

      final result = await versionService.checkForUpdates();

      if (result.hasUpdate && result.metadata != null) {
        final bool isMandatory = result.requirement == UpdateRequirement.mandatory;
        
        if (isMandatory && mounted) {
          setState(() {
            _isUpdateForced = true; // Drop all pointer events to the underlying app shell
          });
        }

        final currentContext = rootNavigatorKey.currentContext;
        if (currentContext != null && currentContext.mounted) {
          showDialog(
            context: currentContext,
            barrierDismissible: !isMandatory,
            builder: (context) => UpdatePromptDialog(
              metadata: result.metadata!,
              currentVersionDisplay: result.currentVersionDisplay,
              isForced: isMandatory,
            ),
          );
        }
      }
    } catch (e) {
      // Fail silently to prevent interrupting app entry flows during offline states
      print('--> [AppRoot] Background version evaluation bypassed gracefully: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    // Physically block interactions with the underlying screen if a mandatory update is required
    return IgnorePointer(
      ignoring: _isUpdateForced,
      child: widget.child,
    );
  }
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: rootNavigatorKey,
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
      // Intercept initialization lifecycle wrapping primary target pages
      home: const UpdatePromptInterceptor(
        child: OnboardingRegistrationScreen(),
      ),
    );
  }
}